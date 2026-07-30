import { cn } from "@/shared/lib";

/**
 * Fixed confetti field for the «Регистрация завершена!» sheet.
 *
 * The positions are a hand-authored constant, not `Math.random()`: a random
 * layout re-scatters on every re-render (and would differ between SSR-less
 * hydration passes and screenshots), which turns a celebration into a flicker.
 * Values are percentages of the box — [x, y, rotation, scale].
 */
const PIECES: readonly (readonly [number, number, number, number])[] = [
  [6, 12, -20, 1], [14, 32, 35, 0.8], [9, 58, 12, 0.9], [18, 74, -45, 0.7],
  [24, 8, 55, 0.85], [31, 26, -12, 1], [27, 48, 70, 0.75], [36, 64, 22, 0.9],
  [44, 5, -35, 0.8], [48, 22, 48, 0.7], [41, 40, 15, 0.95], [52, 56, -60, 0.8],
  [58, 10, 28, 0.9], [64, 30, -18, 0.75], [69, 50, 62, 1], [61, 70, -28, 0.7],
  [76, 6, 40, 0.85], [82, 24, -50, 0.9], [88, 44, 18, 0.8], [79, 60, 65, 0.75],
  [93, 14, -30, 0.7], [96, 36, 25, 0.9], [3, 42, 50, 0.75], [12, 88, -15, 0.8],
  [34, 84, 38, 0.7], [56, 80, -42, 0.85], [72, 86, 20, 0.75], [90, 68, -55, 0.8],
];

interface ConfettiProps {
  className?: string;
}

export function Confetti({ className }: ConfettiProps) {
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}
    >
      {PIECES.map(([x, y, rotate, scale], index) => (
        <span
          key={index}
          className={cn(
            "absolute block h-2 w-1 rounded-[1px] bg-brand",
            // Alternating opacity gives the drift depth without a second colour.
            index % 3 === 0 ? "opacity-90" : index % 3 === 1 ? "opacity-60" : "opacity-35",
          )}
          style={{
            left: `${x}%`,
            top: `${y}%`,
            transform: `rotate(${rotate}deg) scale(${scale})`,
          }}
        />
      ))}
    </div>
  );
}
