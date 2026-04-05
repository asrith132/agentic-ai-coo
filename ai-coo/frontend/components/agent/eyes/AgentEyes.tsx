"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { EYE_EMOTIONS } from "./eye-emotions";
import type { EyeMood } from "./eye-types";
import {
  pickEyeVariantForMood,
  resolveDefaultEyeVariant,
} from "./eye-utils";
import { Eye } from "./Eye";

type AgentEyesProps = {
  mood?: EyeMood;
  small?: boolean;
  showAmbientGlow?: boolean;
  /** Extra classes on the eye pair row (e.g. tighter `gap-4` for splash logo) */
  pairClassName?: string;
  /**
   * After hydration, pick a random variant within the mood (no SSR mismatch).
   * Set false for splash / logos to avoid a post-mount visual jump.
   */
  shuffleVariantAfterMount?: boolean;
};

function blinkDelayMs(interval: [number, number] | undefined) {
  if (!interval || interval.length < 2) {
    return 1800 + Math.random() * 400;
  }
  const [min, max] = interval;
  return min + Math.random() * (max - min);
}

export default function AgentEyes({
  mood = "idle",
  small = false,
  showAmbientGlow = true,
  pairClassName,
  shuffleVariantAfterMount = true,
}: AgentEyesProps) {
  const [blink, setBlink] = useState(false);
  /** Avoid SSR/client Math.random mismatch: first paint matches server, then pick variant on client. */
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const moodConfig = useMemo(() => EYE_EMOTIONS[mood], [mood]);
  const variant = useMemo(() => {
    if (!mounted || !shuffleVariantAfterMount) {
      return resolveDefaultEyeVariant(moodConfig);
    }
    return pickEyeVariantForMood(moodConfig);
  }, [mounted, moodConfig, shuffleVariantAfterMount]);

  useEffect(() => {
    let timeoutId: number;

    const loop = () => {
      timeoutId = window.setTimeout(() => {
        setBlink(true);
        window.setTimeout(() => setBlink(false), 95);
        loop();
      }, blinkDelayMs(variant.blinkInterval));
    };

    loop();
    return () => window.clearTimeout(timeoutId);
  }, [mood, variant]);

  return (
    <div className="relative flex items-center justify-center">
      {showAmbientGlow && (
        <div
          className="absolute inset-x-0 top-1/2 mx-auto h-52 w-[32rem] max-w-[90vw] -translate-y-1/2 rounded-full bg-orange-300/10 blur-3xl"
          style={{
            opacity:
              Math.round(Math.min(1, 0.45 + variant.glowOpacity * 1.2) * 1000) /
              1000,
          }}
        />
      )}

      <motion.div
        animate={{ scale: variant.scale ?? 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 24 }}
        className="relative z-20"
      >
        <motion.div
          className={cn(
            "flex items-center justify-center gap-6 sm:gap-10",
            pairClassName,
          )}
          animate={{
            y: [0, -4, 0],
            rotate: variant.rotate ?? [0, 0.6, 0],
          }}
          transition={{
            y: { duration: 3.2, repeat: Infinity, ease: "easeInOut" },
            rotate: variant.rotate
              ? {
                  duration: variant.duration,
                  repeat: Infinity,
                  ease: "easeInOut",
                }
              : { duration: 4, repeat: Infinity, ease: "easeInOut" },
          }}
        >
          <Eye side="left" variant={variant} blink={blink} small={small} />
          <Eye side="right" variant={variant} blink={blink} small={small} />
        </motion.div>
      </motion.div>
    </div>
  );
}
