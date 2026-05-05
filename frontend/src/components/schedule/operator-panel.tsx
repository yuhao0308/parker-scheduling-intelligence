"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { AutoGenTab } from "@/components/schedule/auto-gen-tab";
import { CalloutTab } from "@/components/schedule/callout-tab";
import { IndividualScheduleTab } from "@/components/schedule/individual-schedule-tab";
import type { CalendarLoadingScope } from "@/lib/types";

type PanelMode = "autogen" | "callout" | "individual";

interface OperatorPanelProps {
  year: number;
  month: number;
  periodStart: Date;
  periodEnd: Date;
  onLoadingScopeChange?: (scope: CalendarLoadingScope | null) => void;
  selectedEmployeeIds: Set<string>;
  onSelectedEmployeeIdsChange: (next: Set<string>) => void;
}

/**
 * Right-column operator cockpit.
 *
 * Three tabs: Auto Gen (weekly/monthly schedule confirmations), Callout
 * (same-day replacements), and Individual (filter the calendar to one or
 * more employees).
 */
export function OperatorPanel({
  year,
  month,
  periodStart,
  periodEnd,
  onLoadingScopeChange,
  selectedEmployeeIds,
  onSelectedEmployeeIdsChange,
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
          hint="Build week or month"
        />
        <TabButton
          active={mode === "callout"}
          onClick={() => setMode("callout")}
          label="Callout"
          hint="Same-day replacements"
        />
        <TabButton
          active={mode === "individual"}
          onClick={() => setMode("individual")}
          label="Individual"
          hint="Filter by employee"
          badge={
            selectedEmployeeIds.size > 0
              ? String(selectedEmployeeIds.size)
              : undefined
          }
        />
      </div>

      {/* Tab body */}
      <div className="p-3">
        {mode === "autogen" ? (
          <AutoGenTab
            year={year}
            month={month}
            periodStart={periodStart}
            periodEnd={periodEnd}
            onLoadingScopeChange={onLoadingScopeChange}
          />
        ) : mode === "callout" ? (
          <CalloutTab year={year} month={month} />
        ) : (
          <IndividualScheduleTab
            selectedEmployeeIds={selectedEmployeeIds}
            onSelectedEmployeeIdsChange={onSelectedEmployeeIdsChange}
          />
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
  badge,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint: string;
  badge?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex-1 px-3 py-2 text-sm font-medium border-b-2 transition-colors relative",
        active
          ? "border-primary text-foreground bg-background"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      <div className="flex items-center justify-center gap-1.5">
        <span>{label}</span>
        {badge && (
          <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
            {badge}
          </span>
        )}
      </div>
      <div className="text-[10px] font-normal text-muted-foreground">{hint}</div>
    </button>
  );
}
