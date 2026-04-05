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

/** SessionStorage key for resuming a line after guest hits `login_required`. */
export const PM_PENDING_VOICE_TRANSCRIPT_KEY = "pm_pending_voice_transcript";

export type UseRealtimeMicOptions = {
  getAccessToken?: () => Promise<string | null>;
};

/**
 * High-level voice UI phase for the assistant experience (eyes, bars, panels).
 * `thinking` stays true until the model response is back and playback is about to start
 * (or immediately if there is nothing to play).
 */
export type VoiceExperienceState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "complete";

export function useRealtimeMicTranscription(
  options?: UseRealtimeMicOptions,
) {
  const [typedText, setTypedText] = useState("");
  const [assistantReply, setAssistantReply] = useState("");
  /** Bumps each successful reply so the assistant panel remounts even if `spoken_reply` text repeats. */
  const [assistantReplyTurnId, setAssistantReplyTurnId] = useState(0);
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
      },
      playback?: {
        onAfterSpeaking?: () => void;
        /** End “thinking” / `voiceProcessing`; call when output begins or cannot play. */
        onPlaybackStarted?: () => void;
      },
    ) => {
      const text = rawText.trim();
      const hasMp3 =
        Boolean(tts?.audio_base64) &&
        !tts?.error &&
        typeof window !== "undefined";

      let playbackNotified = false;
      const notifyPlaybackStarted = () => {
        if (playbackNotified) return;
        playbackNotified = true;
        playback?.onPlaybackStarted?.();
      };

      const beginAudibleSpeaking = () => {
        notifyPlaybackStarted();
        isAgentSpeakingRef.current = true;
        setIsAgentSpeaking(true);
      };

      if (typeof window === "undefined" || (!text && !hasMp3)) {
        notifyPlaybackStarted();
        return;
      }

      const s = scribeRef.current;
      if (!s) {
        notifyPlaybackStarted();
        return;
      }

      const resumeAfter = micSessionActiveRef.current && s.isConnected;

      if (s.isConnected) {
        s.disconnect();
      }

      const afterSpeaking = playback?.onAfterSpeaking;

      const finishSpeaking = () => {
        isAgentSpeakingRef.current = false;
        setIsAgentSpeaking(false);
        if (afterSpeaking) {
          afterSpeaking();
          return;
        }
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
          notifyPlaybackStarted();
          finishSpeaking();
          return;
        }
        beginAudibleSpeaking();
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
              { onStarted: beginAudibleSpeaking },
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
        const token = (await options?.getAccessToken?.()) ?? null;

        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }

        const transcriptUrl = `${base}/api/pm/voice/transcript?include_tts_audio=true`;
        const res = await fetch(
          transcriptUrl,
          {
            method: "POST",
            headers,
            body: JSON.stringify({
              transcript: text,
              conversation: conversationRef.current,
            }),
          },
        );
        const data = (await res.json()) as {
          detail?: string;
          result?: {
            status?: string;
            redirect_to?: string | null;
            spoken_reply?: string;
            tts?: {
              audio_base64?: string;
              content_type?: string;
              error?: string;
              tts_enabled?: boolean;
              message?: string;
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
            hasAudio: Boolean(data.result?.tts?.audio_base64),
            error: data.result?.tts?.error,
            contentType: data.result?.tts?.content_type,
          });
        }
        const spoken = data.result?.spoken_reply ?? "";

        const needsLoginRedirect =
          data.result?.status === "login_required" ||
          data.result?.redirect_to === "/login";
        if (needsLoginRedirect && typeof window !== "undefined") {
          sessionStorage.setItem(PM_PENDING_VOICE_TRANSCRIPT_KEY, text);
        }

        conversationRef.current = [
          ...conversationRef.current,
          { role: "user", content: text },
          { role: "assistant", content: spoken },
        ];

        setAssistantReply(spoken);
        setAssistantReplyTurnId((n) => n + 1);
        setTypedText("");

        const postListenLoginRedirect =
          needsLoginRedirect && typeof window !== "undefined"
            ? () => {
                window.setTimeout(() => {
                  window.location.assign("/login");
                }, 450);
              }
            : undefined;

        playAssistantOutput(spoken, data.result?.tts, {
          onPlaybackStarted: () => setVoiceProcessing(false),
          onAfterSpeaking: postListenLoginRedirect,
        });
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Voice request failed";
        setError(msg);
        setVoiceProcessing(false);
      }
    },
    [playAssistantOutput, options?.getAccessToken],
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
    const s = scribeRef.current;
    if (s) {
      s.disconnect();
      if (s.partialTranscript?.trim()) {
        setTypedText(s.partialTranscript.trim());
      }
    }
    // Do not cancel speechSynthesis or clear isAgentSpeaking — turning the mic off
    // only stops capture; assistant TTS may continue with the mic off.
  }, []);

  const setTranscriptFromTyping = useCallback((value: string) => {
    if (micSessionActiveRef.current) return;
    setTypedText(value);
  }, []);

  /** Same pipeline as a committed STT line; call when the user sends typed input (e.g. Enter). */
  const submitTranscriptFromInput = useCallback(
    (raw: string) => {
      if (micSessionActiveRef.current) return;
      const text = raw.trim();
      if (!text) return;
      unlockWebAudioOnUserGesture(assistantAudioCtxRef);
      setTypedText("");
      enqueueCommitted(text);
    },
    [enqueueCommitted],
  );

  const status: MicTranscriptionStatus =
    scribe.status === "connecting"
      ? "connecting"
      : scribe.isConnected || (micSessionActive && isAgentSpeaking)
        ? "listening"
        : "idle";

  const displayText = scribe.isConnected
    ? scribe.partialTranscript
    : typedText;

  /** True while connecting or sending a transcript — used to block *starting* the mic, not stopping. */
  const micBusy =
    scribe.status === "connecting" || voiceProcessing;

  const voiceExperienceState: VoiceExperienceState = (() => {
    if (isAgentSpeaking) return "speaking";
    if (voiceProcessing) return "thinking";
    if (micSessionActive && scribe.status === "connecting") return "connecting";
    if (micSessionActive && scribe.isConnected) return "listening";
    if (assistantReply.trim()) return "complete";
    return "idle";
  })();

  return {
    displayText,
    assistantReply,
    assistantReplyTurnId,
    isListening: micSessionActive,
    status,
    voiceExperienceState,
    error,
    voiceProcessing,
    isAgentSpeaking,
    startListening,
    stopListening,
    setTranscriptFromTyping,
    submitTranscriptFromInput,
    micBusy,
    getConversationSnapshot: () => [...conversationRef.current],
  };
}
