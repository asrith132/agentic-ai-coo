"use client";

import { useCallback, useState } from "react";

export type MicTranscriptionStatus = "idle" | "connecting" | "listening";

// TODO: Replace with real-time mic + STT when backend exists.

export function useRealtimeMicTranscription() {
  const [displayText, setDisplayText] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [status, setStatus] = useState<MicTranscriptionStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const startListening = useCallback(() => {
    setError(null);
    setStatus("connecting");
    window.setTimeout(() => {
      setStatus("listening");
      setIsListening(true);
    }, 200);
  }, []);

  const stopListening = useCallback(() => {
    setIsListening(false);
    setStatus("idle");
  }, []);

  const setTranscriptFromTyping = useCallback((value: string) => {
    setDisplayText(value);
  }, []);

  return {
    displayText,
    isListening,
    status,
    error,
    startListening,
    stopListening,
    setTranscriptFromTyping,
  };
}
