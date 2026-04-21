"use client";

import { useEffect, useState } from "react";

/**
 * Runs a tick-down countdown while `active` is true. When remaining hits 0,
 * fires `onElapsed` once and clears the interval. Designed for the demo's
 * enforced short timeouts (15s) while the UI displays a longer human label
 * like "2 hours" or "15 minutes" separately.
 *
 * Resets whenever `seconds` or `active` changes.
 */
export function useCountdown(
  seconds: number,
  active: boolean,
  onElapsed: () => void,
): number {
  const [remaining, setRemaining] = useState(seconds);

  useEffect(() => {
    if (!active) return;
    setRemaining(seconds);
    const start = Date.now();
    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - start) / 1000);
      const next = Math.max(0, seconds - elapsed);
      setRemaining(next);
      if (next === 0) {
        clearInterval(interval);
        onElapsed();
      }
    }, 250);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, seconds]);

  return remaining;
}
