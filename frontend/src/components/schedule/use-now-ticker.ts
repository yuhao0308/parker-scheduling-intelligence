"use client";

import { useEffect, useState } from "react";

/**
 * One shared ticker for the whole panel — returns a `now` timestamp (ms) that
 * re-renders the panel once per `intervalMs` while `active` is true.
 *
 * Replaces per-row `useCountdown` hooks that each spawned their own interval
 * and fired independent TIMEOUT mutations when they hit zero. Callers derive
 * per-entry remaining seconds from `sent_at + timeout_seconds - now`.
 */
export function useNowTicker(active: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs]);
  return now;
}
