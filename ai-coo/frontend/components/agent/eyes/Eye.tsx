"use client";

import { motion } from "framer-motion";
import type { EyeAnimationVariant } from "./eye-types";

type EyeProps = {
  side: "left" | "right";
  variant: EyeAnimationVariant;
  blink: boolean;
  small?: boolean;
};

function o(base: number, gScale: number, g: number) {
  return Math.round(Math.min(1, base + g * gScale) * 1000) / 1000;
}

export function Eye({ side, variant, blink, small = false }: EyeProps) {
  const { x, y, duration } = variant;
  const g = variant.glowOpacity;

  return (
    <motion.div
      animate={{ scaleY: blink ? 0.16 : 1 }}
      transition={{ duration: blink ? 0.09 : 0.18 }}
      className={`relative ${
        small ? "h-20 w-20 sm:h-24 sm:w-24" : "h-40 w-40 sm:h-52 sm:w-52"
      } ${side === "left" ? "rotate-[-4deg]" : "rotate-[4deg]"}`}
    >
      <div
        className="absolute inset-0 rounded-[36%] border border-orange-200/20 bg-[radial-gradient(circle_at_50%_45%,rgba(255,227,168,0.75)_0%,rgba(255,176,73,0.5)_25%,rgba(255,120,28,0.28)_55%,rgba(110,34,8,0.72)_100%)] shadow-[0_0_28px_rgba(255,155,60,0.16),inset_0_0_20px_rgba(255,220,150,0.1)]"
        style={{ opacity: o(0.72, 1, g) }}
      />

      <div
        className="absolute inset-[8%] rounded-[34%] bg-[radial-gradient(circle_at_50%_48%,rgba(255,235,190,0.36)_0%,rgba(255,153,55,0.16)_46%,transparent_72%)] blur-md"
        style={{ opacity: o(0.45, 1.2, g) }}
      />

      <motion.div
        className="absolute inset-0"
        animate={{ x, y }}
        transition={{ duration, repeat: Infinity, ease: "easeInOut" }}
      >
        <div
          className={`absolute left-1/2 top-[48%] -translate-x-1/2 -translate-y-1/2 rounded-[44%] bg-[radial-gradient(circle_at_45%_40%,#fffef8_0%,#fff6dc_34%,#ffd891_62%,rgba(255,216,145,0.18)_100%)] blur-[0.4px] shadow-[0_0_18px_rgba(255,244,215,0.7)] ${
            small ? "h-10 w-8 sm:h-12 sm:w-10" : "h-20 w-16 sm:h-28 sm:w-24"
          }`}
          style={{ opacity: o(0.82, 0.35, g) }}
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
