"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff } from "lucide-react";
import { Ripple as RippleComponent } from "@/components/ui/ripple";
import { useRealtimeMicTranscription } from "@/hooks/useRealtimeMicTranscription";

type EyeMood = "idle" | "listening" | "thinking";

function useEyeDrift(mood: EyeMood) {
  return useMemo(() => {
    if (mood === "thinking") {
      return {
        x: [0, -2, 1.5, 0],
        y: [0, -1.5, -0.5, 0],
        duration: 2.6,
      };
    }

    if (mood === "listening") {
      return {
        x: [0, 1.5, -1, 0],
        y: [0, 0.8, 0.2, 0],
        duration: 2.2,
      };
    }

    return {
      x: [0, 1, -0.7, 0],
      y: [0, -0.8, 0.2, 0],
      duration: 4,
    };
  }, [mood]);
}

function GlowingEye({
  side,
  mood,
  blink,
  small = false,
}: {
  side: "left" | "right";
  mood: EyeMood;
  blink: boolean;
  small?: boolean;
}) {
  const { x, y, duration } = useEyeDrift(mood);

  return (
    <motion.div
      animate={{ scaleY: blink ? 0.16 : 1 }}
      transition={{ duration: blink ? 0.09 : 0.18 }}
      className={`relative ${
        small ? "h-20 w-20 sm:h-24 sm:w-24" : "h-40 w-40 sm:h-52 sm:w-52"
      } ${side === "left" ? "rotate-[-4deg]" : "rotate-[4deg]"}`}
    >
      <div className="absolute inset-0 rounded-[36%] border border-orange-200/20 bg-[radial-gradient(circle_at_50%_45%,rgba(255,227,168,0.75)_0%,rgba(255,176,73,0.5)_25%,rgba(255,120,28,0.28)_55%,rgba(110,34,8,0.72)_100%)] shadow-[0_0_28px_rgba(255,155,60,0.16),inset_0_0_20px_rgba(255,220,150,0.1)]" />

      <div className="absolute inset-[8%] rounded-[34%] bg-[radial-gradient(circle_at_50%_48%,rgba(255,235,190,0.36)_0%,rgba(255,153,55,0.16)_46%,transparent_72%)] blur-md" />

      <motion.div
        className="absolute inset-0"
        animate={{ x, y }}
        transition={{ duration, repeat: Infinity, ease: "easeInOut" }}
      >
        <div
          className={`absolute left-1/2 top-[48%] -translate-x-1/2 -translate-y-1/2 rounded-[44%] bg-[radial-gradient(circle_at_45%_40%,#fffef8_0%,#fff6dc_34%,#ffd891_62%,rgba(255,216,145,0.18)_100%)] blur-[0.4px] shadow-[0_0_18px_rgba(255,244,215,0.7)] ${
            small ? "h-10 w-8 sm:h-12 sm:w-10" : "h-20 w-16 sm:h-28 sm:w-24"
          }`}
        />
        <div
          className={`absolute right-[21%] top-[18%] rounded-full bg-white/75 blur-[0.5px] ${
            small ? "h-2 w-2 sm:h-2.5 sm:w-2.5" : "h-3 w-3 sm:h-4 sm:w-4"
          }`}
        />
      </motion.div>
    </motion.div>
  );
}

function EyesHero({ mood }: { mood: EyeMood }) {
  const [blink, setBlink] = useState(false);

  useEffect(() => {
    let timeoutId: number;

    const loop = () => {
      timeoutId = window.setTimeout(() => {
        setBlink(true);
        window.setTimeout(() => setBlink(false), 95);
        loop();
      }, 1800 + Math.random() * 2200);
    };

    loop();

    return () => window.clearTimeout(timeoutId);
  }, []);

  return (
    <div className="relative flex items-center justify-center">
      <div className="absolute inset-x-0 top-1/2 mx-auto h-52 w-[32rem] -translate-y-1/2 rounded-full bg-orange-300/10 blur-3xl" />

      <motion.div
        className="relative z-20 flex items-center justify-center gap-6 sm:gap-10"
        animate={{ y: [0, -4, 0] }}
        transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
      >
        <GlowingEye side="left" mood={mood} blink={blink} />
        <GlowingEye side="right" mood={mood} blink={blink} />
      </motion.div>
    </div>
  );
}

function MinimalLogo() {
  const [blink, setBlink] = useState(false);

  useEffect(() => {
    let timeoutId: number;

    const loop = () => {
      timeoutId = window.setTimeout(() => {
        setBlink(true);
        window.setTimeout(() => setBlink(false), 90);
        loop();
      }, 1600 + Math.random() * 1800);
    };

    loop();

    return () => window.clearTimeout(timeoutId);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: 6 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 1.02 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="relative flex flex-col items-center justify-center"
    >
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="h-40 w-40 rounded-full bg-orange-300/8 blur-3xl" />
      </div>

      <div className="pointer-events-none absolute inset-0 opacity-20">
        <RippleComponent />
      </div>

      <div className="relative z-10 flex items-center justify-center gap-4">
        <GlowingEye side="left" mood="idle" blink={blink} small />
        <GlowingEye side="right" mood="idle" blink={blink} small />
      </div>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.65 }}
        exit={{ opacity: 0 }}
        transition={{ delay: 0.15, duration: 0.4 }}
        className="relative z-10 mt-5 text-xs tracking-[0.28em] text-white/45 uppercase"
      >
        Agrim AI
      </motion.p>
    </motion.div>
  );
}

function ChatBar({
  listening,
  value,
  onChange,
  micListening,
  micBusy,
  onMicToggle,
}: {
  listening: boolean;
  value: string;
  onChange: (next: string) => void;
  micListening: boolean;
  micBusy: boolean;
  onMicToggle: () => void;
}) {
  return (
    <div className="w-full max-w-xl">
      <motion.div
        animate={
          listening
            ? {
                boxShadow: [
                  "0 0 0 rgba(255,200,120,0)",
                  "0 0 18px rgba(255,200,120,0.12)",
                  "0 0 0 rgba(255,200,120,0)",
                ],
                borderColor: [
                  "rgba(255,255,255,0.12)",
                  "rgba(255,214,160,0.28)",
                  "rgba(255,255,255,0.12)",
                ],
              }
            : {
                boxShadow: "0 0 0 rgba(255,200,120,0)",
                borderColor: "rgba(255,255,255,0.1)",
              }
        }
        transition={{
          duration: 1.8,
          repeat: listening ? Infinity : 0,
          ease: "easeInOut",
        }}
        className="rounded-full border bg-white/[0.03] px-4 py-3 backdrop-blur-md sm:px-5"
      >
        <div className="flex items-center gap-2 sm:gap-3">
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            readOnly={micListening}
            placeholder="Tap mic, then speak — text appears here"
            title={
              micListening
                ? "Speaking… turn off mic to type with the keyboard."
                : undefined
            }
            className="h-10 min-w-0 flex-1 bg-transparent text-sm text-white/80 outline-none placeholder:text-white/25 read-only:cursor-default"
          />
          <button
            type="button"
            onClick={onMicToggle}
            disabled={micBusy}
            aria-pressed={micListening}
            aria-label={micListening ? "Stop microphone" : "Start microphone"}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition ${
              micListening
                ? "border-orange-300/40 bg-orange-400/15 text-orange-100"
                : "border-white/12 bg-white/[0.06] text-white/70 hover:border-white/20 hover:text-white/90"
            } disabled:cursor-not-allowed disabled:opacity-40`}
          >
            {micListening ? (
              <MicOff className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

export default function AgentFaceUI() {
  const [showLogo, setShowLogo] = useState(true);

  const {
    displayText,
    isListening: micListening,
    error: micError,
    voiceProcessing,
    isAgentSpeaking,
    startListening,
    stopListening,
    setTranscriptFromTyping,
    micBusy,
  } = useRealtimeMicTranscription();

  const mood: EyeMood = voiceProcessing
    ? "thinking"
    : isAgentSpeaking
      ? "thinking"
      : micListening
        ? "listening"
        : "idle";

  const listening = micListening || isAgentSpeaking;

  useEffect(() => {
    const id = window.setTimeout(() => {
      setShowLogo(false);
    }, 1600);

    return () => window.clearTimeout(id);
  }, []);

  return (
    <main className="relative min-h-screen overflow-hidden bg-black text-white">
      <AnimatePresence mode="wait">
        {showLogo ? (
          <motion.div
            key="logo"
            className="absolute inset-0 z-50 flex items-center justify-center bg-black"
            exit={{ opacity: 0 }}
            transition={{ duration: 0.45 }}
          >
            <MinimalLogo />
          </motion.div>
        ) : (
          <motion.div
            key="page"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="contents"
          >
            <div className="absolute inset-0 z-0 overflow-hidden">
              <motion.div
                animate={{
                  opacity: isAgentSpeaking ? 0.4 : 0,
                  scale: isAgentSpeaking ? 2.8 : 0.985,
                }}
                transition={{ duration: 0.35, ease: "easeInOut" }}
                className="absolute inset-0"
              >
                <RippleComponent />
              </motion.div>
            </div>

            <div className="relative z-10 flex min-h-screen flex-col items-center justify-between px-6 py-10 sm:px-8 sm:py-12">
              <div />

              <div className="flex w-full flex-1 items-center justify-center">
                <EyesHero mood={mood} />
              </div>

              <div className="flex w-full max-w-xl flex-col items-center gap-2">
                <ChatBar
                  listening={listening}
                  value={displayText}
                  onChange={setTranscriptFromTyping}
                  micListening={micListening}
                  micBusy={micBusy}
                  onMicToggle={() =>
                    micListening ? stopListening() : void startListening()
                  }
                />
                {micError ? (
                  <p className="max-w-xl text-center text-xs text-red-400/90">
                    {micError}
                  </p>
                ) : null}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}