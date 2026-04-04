export type EyeMood =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "happy"
  | "curious"
  | "confused"
  | "sleepy"
  | "alert";

export type EyeShapeVariant =
  | "neutral"
  | "wide"
  | "narrow"
  | "soft"
  | "sharp"
  | "droopy"
  | "squint"
  | "uneven";

export type EyeAnimationVariant = {
  name: string;

  /** Lateral drift of the inner eye core */
  x: number[];

  /** Vertical drift of the inner eye core */
  y: number[];

  /** Whole-eye bobbing or nodding motion */
  nod?: number[];

  /** Time for one motion cycle */
  duration: number;

  /** Random blink delay in ms: [min, max] */
  blinkInterval: [number, number];

  /** Outer glow strength */
  glowOpacity: number;

  /** Optional overall scale of the eye */
  scale?: number;

  /** Optional rotation keyframes in degrees */
  rotate?: [number, number, number];

  /** Visual expression cues */
  shape?: EyeShapeVariant;
  openness?: number;
  widthScale?: number;
  heightScale?: number;
  innerGlow?: number;

  /** If true, this variant should feel less symmetrical */
  asymmetric?: boolean;
};

export type EyeMoodConfig = {
  defaultVariant: string;
  variants: EyeAnimationVariant[];
};