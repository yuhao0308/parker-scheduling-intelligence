"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Renders a number that briefly scales up when it increments. Useful for
 * counters that change as a result of user action (assigned/required, score,
 * etc.) — gives a confirmation pop without any toast.
 *
 * Decreases are not popped, so unstaffing doesn't celebrate.
 *
 * Uses React's "set state during render" idiom to react to prop changes
 * synchronously, avoiding the cascading-render warning that comes with
 * doing the same work in useEffect.
 * https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes
 */
export function NumberPop({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const [prev, setPrev] = useState(value);
  const [popKey, setPopKey] = useState(0);

  if (value !== prev) {
    setPrev(value);
    if (value > prev) setPopKey((k) => k + 1);
  }

  return (
    <span
      key={popKey}
      className={cn("inline-block", popKey > 0 && "motion-safe:animate-pop", className)}
    >
      {value}
    </span>
  );
}
