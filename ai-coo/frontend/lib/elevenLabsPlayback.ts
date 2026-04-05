import type { MutableRefObject } from "react";

/**
 * Play ElevenLabs MP3 (base64) in the browser.
 *
 * Browsers often block `new Audio().play()` after an async `fetch` (no user gesture).
 * We unlock an AudioContext on mic tap, then prefer decoding MP3 via Web Audio API.
 */

export function unlockWebAudioOnUserGesture(
  audioCtxRef: MutableRefObject<AudioContext | null>,
): void {
  if (typeof window === "undefined") return;
  const AC =
    window.AudioContext ||
    (
      window as unknown as {
        webkitAudioContext?: typeof AudioContext;
      }
    ).webkitAudioContext;
  if (!AC) return;
  try {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AC();
    }
    void audioCtxRef.current.resume();
  } catch {
    /* ignore */
  }
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

/**
 * Try Web Audio decode + buffer source, then HTMLAudioElement blob playback.
 */
export type PlayMp3Options = {
  /** Fired once when audible playback actually starts (after decode / buffer start or HTMLAudio play). */
  onStarted?: () => void;
};

export async function playMp3Base64(
  audioCtxRef: MutableRefObject<AudioContext | null>,
  base64: string,
  mimeType: string,
  options?: PlayMp3Options,
): Promise<void> {
  const onStarted = options?.onStarted;
  const ctx = audioCtxRef.current;
  if (ctx) {
    await ctx.resume();
    try {
      const raw = base64ToArrayBuffer(base64);
      const audioBuffer = await ctx.decodeAudioData(raw.slice(0));
      await new Promise<void>((resolve, reject) => {
        const src = ctx.createBufferSource();
        src.buffer = audioBuffer;
        src.connect(ctx.destination);
        src.onended = () => resolve();
        try {
          src.start(0);
          onStarted?.();
        } catch (e) {
          reject(e);
        }
      });
      return;
    } catch {
      /* fall through to HTMLAudio */
    }
  }

  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: mimeType || "audio/mpeg" });
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  Object.assign(audio, { playsInline: true });

  try {
    await audio.play();
    onStarted?.();
    await new Promise<void>((resolve, reject) => {
      audio.addEventListener("ended", () => {
        URL.revokeObjectURL(url);
        resolve();
      });
      audio.addEventListener("error", () => {
        URL.revokeObjectURL(url);
        reject(new Error("HTMLAudio error"));
      });
    });
  } catch {
    URL.revokeObjectURL(url);
    throw new Error("HTMLAudio play() blocked or failed");
  }
}
