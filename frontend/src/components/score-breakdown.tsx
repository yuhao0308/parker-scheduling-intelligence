"use client";

import type { ScoreBreakdown as ScoreBreakdownType } from "@/lib/types";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const dimensions: { key: keyof Omit<ScoreBreakdownType, "total">; label: string; color: string }[] = [
  { key: "overtime_headroom", label: "OT Headroom", color: "bg-emerald-500" },
  { key: "proximity", label: "Proximity", color: "bg-blue-500" },
  { key: "clinical_fit", label: "Clinical Fit", color: "bg-violet-500" },
  { key: "float_penalty", label: "Float Penalty", color: "bg-amber-500" },
  { key: "historical_acceptance", label: "Acceptance", color: "bg-rose-400" },
];

export function ScoreBreakdown({ breakdown }: { breakdown: ScoreBreakdownType }) {
  return (
    <div className="flex flex-col gap-1 w-48">
      {dimensions.map(({ key, label, color }) => {
        const value = breakdown[key];
        return (
          <Tooltip key={key}>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground w-16 truncate">{label}</span>
                <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${color}`}
                    style={{ width: `${Math.max(value * 100, 2)}%` }}
                  />
                </div>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {label}: {value.toFixed(3)}
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}
