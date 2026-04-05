import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes (used by `components/ui/ripple.tsx`). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
