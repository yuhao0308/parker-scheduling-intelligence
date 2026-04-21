"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { AutoGenTab } from "@/components/schedule/auto-gen-tab";
import { CalloutTab } from "@/components/schedule/callout-tab";
import type { CalloutResponse, ConfirmationEntry } from "@/lib/types";

type PanelMode = "autogen" | "callout";

interface OperatorPanelProps {
  /** Currently displayed month (drives callout rollup feed) */
  year: number;
  month: number;
  /** Controlled week picker for the Auto-Gen tab */
  weekStart: string;
  onWeekStartChange: (value: string) => void;
  /** Forwarded from Auto-Gen tab when a DECLINED entry fires the one-click replacement path */
  onDeclineReplacement: (
    entry: ConfirmationEntry,
    replacement: CalloutResponse,
  ) => void;
}

/**
 * Right-column operator cockpit.
 *
 * Implements the supervisor mockup's two-tab split: Auto Gen (weekly schedule
 * confirmations) and Callout (same-day replacements). Both tabs live inside a
 * single card so the schedule calendar stays the visual anchor on the left.
 */
export function OperatorPanel({
  year,
  month,
  weekStart,
  onWeekStartChange,
  onDeclineReplacement,
}: OperatorPanelProps) {
  const [mode, setMode] = useState<PanelMode>("autogen");

  return (
    <div className="rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden operator-panel">
      {/* Tab switcher */}
      <div className="flex border-b bg-muted/30">
        <TabButton
          active={mode === "autogen"}
          onClick={() => setMode("autogen")}
          label="Auto Gen"
          hint="Build next week's schedule"
        />
        <TabButton
          active={mode === "callout"}
          onClick={() => setMode("callout")}
          label="Callout"
          hint="Same-day replacements"
        />
      </div>

      {/* Tab body */}
      <div className="p-3">
        {mode === "autogen" ? (
          <AutoGenTab
            weekStart={weekStart}
            onWeekStartChange={onWeekStartChange}
            onDeclineReplacement={onDeclineReplacement}
          />
        ) : (
          <CalloutTab year={year} month={month} />
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  label,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 px-3 py-2 text-sm font-medium border-b-2 transition-colors",
        active
          ? "border-primary text-foreground bg-background"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      <div>{label}</div>
      <div className="text-[10px] font-normal text-muted-foreground">{hint}</div>
    </button>
  );
}
