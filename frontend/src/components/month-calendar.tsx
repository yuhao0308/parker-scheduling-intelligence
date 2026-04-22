"use client";

import { cn } from "@/lib/utils";
import type {
  MonthlySchedule,
  ShiftLabel,
  ShiftSlot,
  ShiftSlotStatus,
} from "@/lib/types";

const WEEKDAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

const SHIFT_ORDER: Array<{ key: ShiftLabel; label: string }> = [
  { key: "DAY", label: "Day" },
  { key: "EVENING", label: "Evening" },
  { key: "NIGHT", label: "Night" },
];

const PILL_CLASSES: Record<ShiftSlotStatus, string> = {
  fully_staffed: "bg-emerald-100 text-emerald-800 border-emerald-300",
  partially_staffed: "bg-amber-100 text-amber-800 border-amber-300",
  callout: "bg-red-100 text-red-800 border-red-300",
  unassigned: "bg-slate-100 text-slate-600 border-slate-300",
};

const DOT_CLASSES: Record<ShiftSlotStatus, string> = {
  fully_staffed: "bg-emerald-500",
  partially_staffed: "bg-amber-400",
  callout: "bg-red-500",
  unassigned: "bg-slate-400",
};

const STATUS_LABEL: Record<ShiftSlotStatus, string> = {
  fully_staffed: "Fully Staffed",
  partially_staffed: "Partially Staffed",
  callout: "Has Call-out",
  unassigned: "Unassigned",
};

export type StatusFilter = "all" | ShiftSlotStatus;

interface MonthCalendarProps {
  data: MonthlySchedule | undefined;
  isLoading: boolean;
  onSlotClick: (slot: ShiftSlot) => void;
  selectedUnit: string | null;
  statusFilter: StatusFilter;
  today: Date;
}

interface PillRow {
  label: string;
  shift: ShiftLabel;
  assigned: number;
  required: number;
  status: ShiftSlotStatus;
  slots: ShiftSlot[];
}

function aggregateDayStatus(
  slots: ShiftSlot[],
  selectedUnit: string | null,
): PillRow[] {
  return SHIFT_ORDER.map(({ key, label }) => {
    const scoped = slots.filter(
      (s) => s.shift_label === key && (!selectedUnit || s.unit_id === selectedUnit),
    );
    const assigned = scoped.reduce(
      (n, s) => n + s.assigned_employees.length,
      0,
    );
    const required = scoped.reduce((n, s) => n + s.required_count, 0);
    const hasCallout = scoped.some((s) => s.unresolved_callout_count > 0);

    let status: ShiftSlotStatus;
    if (hasCallout) status = "callout";
    else if (assigned === 0 && required > 0) status = "unassigned";
    else if (required > 0 && assigned >= required) status = "fully_staffed";
    else status = "partially_staffed";

    return { label, shift: key, assigned, required, status, slots: scoped };
  });
}

function isSameDay(a: Date, b: Date) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function MonthCalendar({
  data,
  isLoading,
  onSlotClick,
  selectedUnit,
  statusFilter,
  today,
}: MonthCalendarProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 text-muted-foreground">
        Loading schedule...
      </div>
    );
  }

  if (!data || data.days.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 text-muted-foreground">
        No schedule data for this month.
      </div>
    );
  }

  const firstDate = new Date(data.days[0].date + "T00:00:00");
  const startDow = firstDate.getDay();
  const totalDays = data.days.length;

  const cells: (number | null)[] = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 0; d < totalDays; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="w-full">
      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 pb-3 text-xs">
        {(Object.keys(STATUS_LABEL) as ShiftSlotStatus[]).map((s) => (
          <div key={s} className="flex items-center gap-1.5">
            <span className={cn("h-2.5 w-2.5 rounded-full", DOT_CLASSES[s])} />
            <span className="text-muted-foreground">{STATUS_LABEL[s]}</span>
          </div>
        ))}
      </div>

      {/* Header row */}
      <div className="grid grid-cols-7 border-b border-t">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="text-center text-[11px] font-semibold tracking-wider text-muted-foreground py-2"
          >
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 border-l">
        {cells.map((dayIdx, cellIdx) => {
          if (dayIdx === null) {
            return (
              <div
                key={`empty-${cellIdx}`}
                className="min-h-32 border-r border-b bg-muted/10"
              />
            );
          }

          const day = data.days[dayIdx];
          const cellDate = new Date(day.date + "T00:00:00");
          const dayNum = cellDate.getDate();
          const isToday = isSameDay(cellDate, today);
          const rows = aggregateDayStatus(day.slots, selectedUnit);

          return (
            <div
              key={day.date}
              className="min-h-32 border-r border-b p-1.5 flex flex-col gap-1"
            >
              <div className="flex items-center">
                <span
                  className={cn(
                    "inline-flex h-6 w-6 items-center justify-center rounded-full text-xs",
                    isToday
                      ? "bg-blue-600 text-white font-semibold"
                      : "text-muted-foreground",
                  )}
                >
                  {String(dayNum).padStart(2, "0")}
                </span>
              </div>

              <div className="flex flex-col gap-1">
                {rows.map((r) => {
                  const faded =
                    statusFilter !== "all" && statusFilter !== r.status;
                  const disabled = r.slots.length === 0;
                  return (
                    <button
                      key={r.shift}
                      type="button"
                      disabled={disabled}
                      onClick={() => r.slots[0] && onSlotClick(r.slots[0])}
                      className={cn(
                        "w-full flex items-center justify-between",
                        "rounded border px-1.5 py-0.5 text-[11px] font-medium",
                        "transition-opacity",
                        PILL_CLASSES[r.status],
                        disabled && "opacity-0 pointer-events-none",
                        !disabled && "hover:opacity-80 cursor-pointer",
                        faded && !disabled && "opacity-25",
                      )}
                      title={`${r.label} — ${STATUS_LABEL[r.status]} (${r.assigned}/${r.required})`}
                    >
                      <span>{r.label}</span>
                      <span className="tabular-nums">
                        {r.assigned}/{r.required}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
