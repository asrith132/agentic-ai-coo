import type { EyeAnimationVariant, EyeMood, EyeMoodConfig } from "./eye-types";

/** Stable variant for a mood (uses `defaultVariant` name). */
export function resolveDefaultEyeVariant(mc: EyeMoodConfig): EyeAnimationVariant {
  const v = mc.variants.find((x) => x.name === mc.defaultVariant);
  return v ?? mc.variants[0];
}

/** Random variant when mood changes (subtle variety within the same mood). */
export function pickEyeVariantForMood(mc: EyeMoodConfig): EyeAnimationVariant {
  const i = Math.floor(Math.random() * mc.variants.length);
  return mc.variants[i] ?? mc.variants[0];
}

export const ALL_EYE_MOODS: EyeMood[] = [
  "idle",
  "listening",
  "thinking",
  "speaking",
  "happy",
  "curious",
  "confused",
  "sleepy",
  "alert",
];

export function isEyeMood(value: string): value is EyeMood {
  return ALL_EYE_MOODS.includes(value as EyeMood);
}

/**
 * Map coarse agent flags from an API into a single eye mood.
 * Adjust when your backend schema is defined.
 */
export function eyeMoodFromAgentState(input: {
  speaking?: boolean;
  listening?: boolean;
  thinking?: boolean;
}): EyeMood {
  if (input.thinking) return "thinking";
  if (input.speaking) return "speaking";
  if (input.listening) return "listening";
  return "idle";
}
