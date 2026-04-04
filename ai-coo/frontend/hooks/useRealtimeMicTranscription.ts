"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useScribe, CommitStrategy } from "@elevenlabs/react";
import {
  playMp3Base64,
  unlockWebAudioOnUserGesture,
} from "@/lib/elevenLabsPlayback";
import { pickAssistantVoice } from "@/lib/speechSynthesisVoice";

export type MicTranscriptionStatus = "idle" | "connecting" | "listening";

export type PmVoiceTurn = { role: "user" | "assistant"; content: string };

function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
}

type ScribeInstance = ReturnType<typeof useScribe>;

function apiBaseUrlOrThrow(): string {
  const base = apiBaseUrl();
  if (!base) {
    throw new Error(
      "Set NEXT_PUBLIC_API_URL (e.g. http://127.0.0.1:8000) in .env.local",
    );
  }
  return base;
}

export function useRealtimeMicTranscription() {
  const [typedText, setTypedText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [voiceProcessing, setVoiceProcessing] = useState(false);
  const [micSessionActive, setMicSessionActive] = useState(false);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);

  const micSessionActiveRef = useRef(false);
  const isAgentSpeakingRef = useRef(false);

  const conversationRef = useRef<PmVoiceTurn[]>([]);
  const pipelineRef = useRef(Promise.resolve());
  const scribeRef = useRef<ScribeInstance | null>(null);
  const assistantVoiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const assistantAudioCtxRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    isAgentSpeakingRef.current = isAgentSpeaking;
  }, [isAgentSpeaking]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;

    const synth = window.speechSynthesis;
    const refreshVoice = () => {
      assistantVoiceRef.current = pickAssistantVoice(synth.getVoices());
    };

    refreshVoice();
    synth.addEventListener("voiceschanged", refreshVoice);
    return () => synth.removeEventListener("voiceschanged", refreshVoice);
  }, []);

  const connectWithTokenFetch = useCallback(async (scribe: ScribeInstance) => {
    const base = apiBaseUrlOrThrow();

    const r = await fetch(`${base}/api/pm/voice/scribe-token`);
    const data = (await r.json()) as {
      token?: string;
      model_id?: string;
      detail?: string;
    };
    if (!r.ok) {
      throw new Error(
        typeof data.detail === "string" ? data.detail : `HTTP ${r.status}`,
      );
    }
    const token = data.token;
    if (!token) {
      throw new Error("Backend returned no scribe token");
    }
    const modelId = data.model_id ?? "scribe_v2_realtime";
    await scribe.connect({
      token,
      modelId,
      commitStrategy: CommitStrategy.VAD,
      microphone: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  }, []);

  const enqueueRef = useRef<(text: string) => void>(() => {});

  const scribe = useScribe({
    modelId: "scribe_v2_realtime",
    commitStrategy: CommitStrategy.VAD,
    onPartialTranscript: () => {
      setError(null);
    },
    onCommittedTranscript: ({ text }) => {
      if (isAgentSpeakingRef.current) return;
      enqueueRef.current(text);
    },
    onError: (err) => {
      const msg =
        err instanceof Error
          ? err.message
          : "ElevenLabs Scribe connection error";
      setError(msg);
    },
  });

  // Keep latest Scribe instance for callbacks (safe: does not trigger re-renders).
  scribeRef.current = scribe;

  const playAssistantOutput = useCallback(
    (
      rawText: string,
      tts?: {
        audio_base64?: string;
        content_type?: string;
        error?: string;
        tts_enabled?: boolean;
        message?: string;
        voice_id?: string;
      },
    ) => {
      const text = rawText.trim();
      const hasMp3 =
        Boolean(tts?.audio_base64) &&
        !tts?.error &&
        typeof window !== "undefined";

      if (typeof window === "undefined" || (!text && !hasMp3)) return;

      const s = scribeRef.current;
      if (!s) return;

      if (s.partialTranscript?.trim()) {
        setTypedText(s.partialTranscript.trim());
      }

      const resumeAfter = micSessionActiveRef.current && s.isConnected;

      if (s.isConnected) {
        s.disconnect();
      }

      isAgentSpeakingRef.current = true;
      setIsAgentSpeaking(true);

      const finishSpeaking = () => {
        isAgentSpeakingRef.current = false;
        setIsAgentSpeaking(false);
        const sc = scribeRef.current;
        if (resumeAfter && micSessionActiveRef.current && sc) {
          connectWithTokenFetch(sc).catch((e) => {
            const msg =
              e instanceof Error ? e.message : "Could not resume microphone";
            setError(msg);
          });
        }
      };

      const playBrowserTts = () => {
        if (!text) {
          finishSpeaking();
          return;
        }
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 1;
        const v =
          assistantVoiceRef.current ??
          pickAssistantVoice(window.speechSynthesis.getVoices());
        if (v) {
          u.voice = v;
        }
        u.addEventListener("end", finishSpeaking);
        u.addEventListener("error", finishSpeaking);
        window.speechSynthesis.speak(u);
      };

      if (hasMp3 && tts?.audio_base64) {
        void (async () => {
          try {
            await playMp3Base64(
              assistantAudioCtxRef,
              tts.audio_base64!,
              tts.content_type ?? "audio/mpeg",
            );
            finishSpeaking();
          } catch {
            if (tts.error) {
              setError(`ElevenLabs playback failed (${tts.error}). Using browser voice.`);
            } else {
              setError(
                "Could not play ElevenLabs audio (browser may have blocked sound). Using browser voice.",
              );
            }
            playBrowserTts();
          }
        })();
        return;
      }

      if (tts?.error && text) {
        setError(`ElevenLabs TTS: ${tts.error}. Using browser voice.`);
      } else if (
        tts?.tts_enabled === false &&
        tts?.message &&
        text
      ) {
        setError(`${tts.message} Using browser voice.`);
      }

      playBrowserTts();
    },
    [connectWithTokenFetch],
  );

  const processCommitted = useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text) return;

      let base: string;
      try {
        base = apiBaseUrlOrThrow();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Missing API URL");
        return;
      }

      setVoiceProcessing(true);
      setError(null);
      try {
        const res = await fetch(
          `${base}/api/pm/voice/transcript?include_tts_audio=true`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              transcript: text,
              conversation: conversationRef.current,
            }),
          },
        );
        const data = (await res.json()) as {
          detail?: string;
          result?: {
            spoken_reply?: string;
            tts?: {
              audio_base64?: string;
              content_type?: string;
              error?: string;
              tts_enabled?: boolean;
              message?: string;
              voice_id?: string;
            };
          };
        };
        if (!res.ok) {
          const msg =
            typeof data.detail === "string"
              ? data.detail
              : `HTTP ${res.status}`;
          throw new Error(msg);
        }
        if (process.env.NODE_ENV === "development") {
          console.log("tts payload", {
            enabled: data.result?.tts?.tts_enabled,
            voiceId: data.result?.tts?.voice_id,
            hasAudio: Boolean(data.result?.tts?.audio_base64),
            error: data.result?.tts?.error,
            contentType: data.result?.tts?.content_type,
          });
        }
        const spoken = data.result?.spoken_reply ?? "";
        conversationRef.current = [
          ...conversationRef.current,
          { role: "user", content: text },
          { role: "assistant", content: spoken },
        ];
        playAssistantOutput(spoken, data.result?.tts);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Voice request failed";
        setError(msg);
      } finally {
        setVoiceProcessing(false);
      }
    },
    [playAssistantOutput],
  );

  const enqueueCommitted = useCallback(
    (text: string) => {
      pipelineRef.current = pipelineRef.current
        .then(() => processCommitted(text))
        .catch(() => {
          /* processCommitted sets error */
        });
    },
    [processCommitted],
  );

  enqueueRef.current = enqueueCommitted;

  const startListening = useCallback(async () => {
    setError(null);
    try {
      apiBaseUrlOrThrow();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Missing API URL");
      return;
    }
    const s = scribeRef.current;
    if (!s) return;

    unlockWebAudioOnUserGesture(assistantAudioCtxRef);

    micSessionActiveRef.current = true;
    setMicSessionActive(true);
    try {
      await connectWithTokenFetch(s);
    } catch (e) {
      micSessionActiveRef.current = false;
      setMicSessionActive(false);
      const msg = e instanceof Error ? e.message : "Could not start microphone";
      setError(msg);
    }
  }, [connectWithTokenFetch]);

  const stopListening = useCallback(() => {
    micSessionActiveRef.current = false;
    setMicSessionActive(false);
    if (typeof window !== "undefined") {
      window.speechSynthesis.cancel();
    }
    isAgentSpeakingRef.current = false;
    setIsAgentSpeaking(false);
    const s = scribeRef.current;
    if (s) {
      s.disconnect();
      if (s.partialTranscript?.trim()) {
        setTypedText(s.partialTranscript.trim());
      }
    }
  }, []);

  const setTranscriptFromTyping = useCallback((value: string) => {
    if (micSessionActiveRef.current) return;
    setTypedText(value);
  }, []);

  const status: MicTranscriptionStatus =
    scribe.status === "connecting"
      ? "connecting"
      : scribe.isConnected || (micSessionActive && isAgentSpeaking)
        ? "listening"
        : "idle";

  const displayText = scribe.isConnected
    ? scribe.partialTranscript
    : typedText;

  const micBusy =
    scribe.status === "connecting" ||
    voiceProcessing ||
    (micSessionActive && isAgentSpeaking && !scribe.isConnected);

  return {
    displayText,
    isListening: micSessionActive,
    status,
    error,
    voiceProcessing,
    isAgentSpeaking,
    startListening,
    stopListening,
    setTranscriptFromTyping,
    micBusy,
    getConversationSnapshot: () => [...conversationRef.current],
  };
}
