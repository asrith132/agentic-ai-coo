"use client";

import * as React from "react";
import {
  type HTMLMotionProps,
  motion,
  type SpringOptions,
  type Transition,
  useMotionValue,
  useReducedMotion,
  useSpring,
} from "motion/react";

import { cn } from "@/lib/utils";

type StarLayerProps = HTMLMotionProps<"div"> & {
  count: number;
  size: number;
  transition: Transition;
  starColor: string;
  blur?: number;
  shadowBlur?: number;
};

function generateStars(count: number, starColor: string, shadowBlur = 0) {
  const shadows: string[] = [];
  for (let i = 0; i < count; i++) {
    const x = Math.floor(Math.random() * 4000) - 2000;
    const y = Math.floor(Math.random() * 4000) - 2000;
    if (shadowBlur > 0) {
      // Soft glow shadow: offset-x offset-y blur spread color
      shadows.push(`${x}px ${y}px ${shadowBlur}px ${Math.ceil(shadowBlur / 2)}px ${starColor}`);
    } else {
      shadows.push(`${x}px ${y}px ${starColor}`);
    }
  }
  return shadows.join(", ");
}

function StarLayer({
  count = 1000,
  size = 1,
  transition = { repeat: Infinity, duration: 50, ease: "linear" },
  starColor = "#fff",
  blur = 0,
  shadowBlur = 0,
  className,
  ...props
}: StarLayerProps) {
  const [boxShadow, setBoxShadow] = React.useState<string>("");
  const shouldReduceMotion = useReducedMotion();

  React.useEffect(() => {
    setBoxShadow(generateStars(count, starColor, shadowBlur));
  }, [count, starColor, shadowBlur]);

  const particleStyle: React.CSSProperties = {
    width: `${size}px`,
    height: `${size}px`,
    boxShadow,
    filter: blur > 0 ? `blur(${blur}px)` : undefined,
    willChange: "filter",
  };

  return (
    <motion.div
      data-slot="star-layer"
      animate={shouldReduceMotion ? {} : { y: [0, -2000] }}
      transition={transition}
      className={cn("absolute top-0 left-0 w-full h-[2000px]", className)}
      {...props}
    >
      <div className="absolute bg-transparent rounded-full" style={particleStyle} />
      <div className="absolute bg-transparent rounded-full top-[2000px]" style={particleStyle} />
    </motion.div>
  );
}

type StarsBackgroundProps = React.ComponentProps<"div"> & {
  factor?: number;
  speed?: number;
  springTransition?: SpringOptions;
  starColor?: string;
  variant?: "dark" | "light";
};

export function StarsBackground({
  children,
  className,
  style,
  factor = 0.05,
  speed = 50,
  springTransition = { stiffness: 50, damping: 20 },
  starColor,
  variant = "dark",
  ...props
}: StarsBackgroundProps) {
  const offsetX = useMotionValue(1);
  const offsetY = useMotionValue(1);
  const shouldReduceMotion = useReducedMotion();

  const springX = useSpring(offsetX, springTransition);
  const springY = useSpring(offsetY, springTransition);

  const handleMouseMove = React.useCallback(
    (e: React.MouseEvent<HTMLDivElement, MouseEvent>) => {
      if (shouldReduceMotion) return;
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;
      offsetX.set(-(e.clientX - centerX) * factor);
      offsetY.set(-(e.clientY - centerY) * factor);
    },
    [offsetX, offsetY, factor, shouldReduceMotion],
  );

  const isDark = variant === "dark";

  return (
    <div
      data-slot="stars-background"
      className={cn(
        "relative size-full overflow-hidden",
        isDark && "bg-[radial-gradient(ellipse_at_bottom,_#0c1420_0%,_#040810_100%)]",
        className,
      )}
      style={{
        ...(isDark ? undefined : { background: "var(--background)" }),
        ...style,
      }}
      onMouseMove={handleMouseMove}
      {...props}
    >
      {isDark ? (
        /* ── Dark variant: crisp white stars ── */
        <motion.div style={{ x: springX, y: springY }}>
          <StarLayer
            count={1000}
            size={1}
            transition={{ repeat: Infinity, duration: speed, ease: "linear" }}
            starColor={starColor ?? "rgba(255,255,255,0.85)"}
          />
          <StarLayer
            count={400}
            size={2}
            transition={{ repeat: Infinity, duration: speed * 2, ease: "linear" }}
            starColor={starColor ?? "rgba(255,255,255,0.85)"}
          />
          <StarLayer
            count={200}
            size={3}
            transition={{ repeat: Infinity, duration: speed * 3, ease: "linear" }}
            starColor={starColor ?? "rgba(255,255,255,0.85)"}
          />
        </motion.div>
      ) : (
        /* ── Light variant: diffused cosmic dust + ambient blobs ── */
        <>
          {/* Ambient gradient blobs — color washes at very low opacity */}
          <div
            className="absolute pointer-events-none"
            style={{
              bottom: "-15%",
              left: "-10%",
              width: "55vw",
              height: "55vw",
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(134,239,172,0.22) 0%, transparent 70%)",
            }}
          />
          <div
            className="absolute pointer-events-none"
            style={{
              top: "-10%",
              right: "-8%",
              width: "45vw",
              height: "45vw",
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(147,197,253,0.22) 0%, transparent 70%)",
            }}
          />
          <div
            className="absolute pointer-events-none"
            style={{
              top: "20%",
              left: "30%",
              width: "60vw",
              height: "35vw",
              borderRadius: "50%",
              background: "radial-gradient(ellipse, rgba(196,181,253,0.18) 0%, transparent 70%)",
            }}
          />
          <div
            className="absolute pointer-events-none"
            style={{
              bottom: "5%",
              right: "15%",
              width: "30vw",
              height: "30vw",
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(253,186,116,0.05) 0%, transparent 70%)",
            }}
          />

          {/* Floating dust particles */}
          <motion.div style={{ x: springX, y: springY }}>
            {/* Fine indigo dust */}
            <StarLayer
              count={900}
              size={2}
              blur={0.8}
              shadowBlur={2}
              transition={{ repeat: Infinity, duration: speed, ease: "linear" }}
              starColor="rgba(99,102,241,0.20)"
            />
            {/* Mint dust */}
            <StarLayer
              count={350}
              size={3}
              blur={1}
              shadowBlur={2}
              transition={{ repeat: Infinity, duration: speed * 2, ease: "linear" }}
              starColor="rgba(134,239,172,0.25)"
            />
            {/* Violet dust — largest, softest */}
            <StarLayer
              count={180}
              size={4}
              blur={1.5}
              shadowBlur={3}
              transition={{ repeat: Infinity, duration: speed * 3, ease: "linear" }}
              starColor="rgba(196,181,253,0.28)"
            />
          </motion.div>
        </>
      )}

      {children}
    </div>
  );
}
