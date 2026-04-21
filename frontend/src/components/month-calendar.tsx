"use client";

import { cn } from "@/lib/utils";
import type {
  CalloutDayCount,
  ConfirmationStatus,
  MonthlySchedule,
  ShiftSlot,
} from "@/lib/types";
import { StatusOrb } from "@/components/schedule/status-orb";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const SHIFT_SHORT: Record<string, string> = {
  DAY: "D",
  EVENING: "E",
  NIGHT: "N",
};

const STATUS_CLASSES: Record<string, string> = {
  assigned: "bg-emerald-100 border-emerald-400 text-emerald-800",
  unassigned: "bg-amber-100 border-amber-300 text-amber-800",
  callout: "bg-red-100 border-red-400 text-red-800 animate-pulse",
};

interface MonthCalendarProps {
  data: MonthlySchedule | undefined;
  isLoading: boolean;
  onSlotClick: (slot: ShiftSlot) => void;
  selectedUnit: string | null;
  /** Optional per-day callout rollup (feeds the red day dot indicator). */
  calloutsByDate?: CalloutDayCount[];
}

const STATUS_PRIORITY: Record<ConfirmationStatus, number> = {
  DECLINED: 5,
  PENDING: 4,
  UNSENT: 3,
  ACCEPTED: 2,
  REPLACED: 1,
};

/** Pick the most actionable confirmation status among a slot's assignees. */
function slotStatus(slot: ShiftSlot): ConfirmationStatus | null {
  let best: ConfirmationStatus | null = null;
  for (const e of slot.assigned_employees) {
    const s = e.confirmation_status;
    if (!s) continue;
    if (!best || STATUS_PRIORITY[s] > STATUS_PRIORITY[best]) {
      best = s;
    }
  }
  return best;
}

function getUnitShort(unitId: string): string {
  return unitId.replace("U-", "");
}

/** Group slots by unit, then aggregate shift statuses per unit for a day. */
function summarizeDaySlots(slots: ShiftSlot[], unitFilter: string | null) {
  const filtered = unitFilter
    ? slots.filter((s) => s.unit_id === unitFilter)
    : slots;

  // Group by unit
  const byUnit = new Map<string, ShiftSlot[]>();
  for (const s of filtered) {
    const existing = byUnit.get(s.unit_id) ?? [];
    existing.push(s);
    byUnit.set(s.unit_id, existing);
  }
  return byUnit;
}

export function MonthCalendar({
  data,
  isLoading,
  onSlotClick,
  selectedUnit,
  calloutsByDate,
}: MonthCalendarProps) {
  const calloutMap = new Map(
    (calloutsByDate ?? []).map((c) => [c.date, c]),
  );
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

  // Figure out what day of week the 1st falls on
  const firstDate = new Date(data.days[0].date + "T00:00:00");
  const startDow = firstDate.getDay(); // 0=Sun
  const totalDays = data.days.length;

  // Build rows of 7 cells
  const cells: (number | null)[] = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 0; d < totalDays; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="w-full">
      {/* Header row */}
      <div className="grid grid-cols-7 border-b">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="text-center text-xs font-semibold text-muted-foreground py-2"
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
                className="min-h-28 border-r border-b bg-muted/20"
              />
            );
          }

          const day = data.days[dayIdx];
          const dayNum = new Date(day.date + "T00:00:00").getDate();
          const byUnit = summarizeDaySlots(day.slots, selectedUnit);
          const isWeekend = cellIdx % 7 === 0 || cellIdx % 7 === 6;
          const callout = calloutMap.get(day.date);
          const hasActiveCallout = (callout?.active ?? 0) > 0;

          return (
            <div
              key={day.date}
              className={cn(
                "min-h-28 border-r border-b p-1 overflow-hidden",
                isWeekend && "bg-muted/10"
              )}
            >
              <div className="flex items-center gap-1 mb-1">
                <span className="text-xs font-medium text-muted-foreground">
                  {dayNum}
                </span>
                {hasActiveCallout && (
                  <span
                    aria-label={`${callout!.active} active callout${callout!.active === 1 ? "" : "s"}`}
                    title={`${callout!.active} active / ${callout!.total} total`}
                    className="h-1.5 w-1.5 rounded-full bg-red-500"
                  />
                )}
              </div>
              <div className="space-y-0.5">
                {Array.from(byUnit.entries())
                  .slice(0, selectedUnit ? undefined : 4) // show max 4 units when not filtered
                  .map(([unitId, unitSlots]) => (
                    <div key={unitId} className="flex items-center gap-0.5">
                      <span className="text-[10px] text-muted-foreground w-7 shrink-0 truncate">
                        {getUnitShort(unitId)}
                      </span>
                      {unitSlots.map((slot) => {
                        const status = slotStatus(slot);
                        return (
                          <button
                            key={`${slot.unit_id}-${slot.shift_label}`}
                            onClick={() => onSlotClick(slot)}
                            className={cn(
                              "text-[9px] font-medium px-1 py-0.5 rounded border cursor-pointer transition-opacity hover:opacity-80 inline-flex items-center gap-0.5",
                              STATUS_CLASSES[slot.status]
                            )}
                            title={`${slot.unit_name} ${slot.shift_label} — ${slot.status} (${slot.assigned_employees.length} staff)${status ? ` · ${status}` : ""}`}
                          >
                            {status && (
                              <StatusOrb
                                status={status}
                                className="!h-1.5 !w-1.5"
                              />
                            )}
                            <span>
                              {SHIFT_SHORT[slot.shift_label] ??
                                slot.shift_label[0]}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  ))}
                {!selectedUnit && byUnit.size > 4 && (
                  <div className="text-[9px] text-muted-foreground">
                    +{byUnit.size - 4} more units
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-emerald-100 border border-emerald-400" />
          Assigned
        </div>
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-amber-100 border border-amber-300" />
          Unassigned
        </div>
        <div className="flex items-center gap-1">
          <span className="w-3 h-3 rounded bg-red-100 border border-red-400" />
          Callout
        </div>
        <div className="text-[10px]">
          D = Day, E = Evening, N = Night
        </div>
      </div>
    </div>
  );
}
