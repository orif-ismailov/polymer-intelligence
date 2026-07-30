import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Countdown timer (seconds). `start(n)` begins a fresh countdown; the returned
 * `remaining` ticks to 0 and `active` reflects whether it's still running.
 */
export function useCountdown() {
  const [remaining, setRemaining] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const start = useCallback(
    (seconds: number) => {
      stop();
      setRemaining(Math.max(0, Math.floor(seconds)));
      if (seconds <= 0) return;
      intervalRef.current = setInterval(() => {
        setRemaining((prev) => {
          if (prev <= 1) {
            stop();
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    },
    [stop],
  );

  useEffect(() => stop, [stop]);

  return { remaining, active: remaining > 0, start, stop };
}
