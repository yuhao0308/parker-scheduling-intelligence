"use client";

import { useState } from "react";
import { CalendarOff, Sparkles } from "lucide-react";
import { cn, MONTH_SHORT } from "@/lib/utils";
import { NumberPop } from "@/components/number-pop";
import { withViewTransition } from "@/lib/view-transition";
import type {
  CalendarLoadingScope,
  DaySchedule,
  MonthlySchedule,
  ShiftLabel,
  ShiftSlot,
  ShiftSlotStatus,
} from "@/lib/types";

const SHIFT_PILL_VT_NAME = "shift-pill-active";

// Status order — used to detect "improvement" (e.g. unassigned → fully_staffed)
// so the pill can flash a green halo. Higher = better.
const STATUS_RANK: Record<ShiftSlotStatus, number> = {
  unassigned: 0,
  partially_staffed: 1,
  fully_staffed: 2,
};

const WEEKDAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

const SHIFT_ORDER: Array<{ key: ShiftLabel; label: string }> = [
  { key: "DAY", label: "Day" },
  { key: "EVENING", label: "Evening" },
  { key: "NIGHT", label: "Night" },
];

const PILL_CLASSES: Record<ShiftSlotStatus, string> = {
  fully_staffed: "bg-emerald-100 text-emerald-800 border-emerald-300",
  partially_staffed: "bg-amber-100 text-amber-800 border-amber-300",
  unassigned: "bg-slate-100 text-slate-600 border-slate-300",
};

const DOT_CLASSES: Record<ShiftSlotStatus, string> = {
  fully_staffed: "bg-emerald-500",
  partially_staffed: "bg-amber-400",
  unassigned: "bg-slate-400",
};

const STATUS_LABEL: Record<ShiftSlotStatus, string> = {
  fully_staffed: "Fully Staffed",
  partially_staffed: "Partially Staffed",
  unassigned: "Unassigned",
};

export type StatusFilter = "all" | ShiftSlotStatus;

interface MonthCalendarProps {
  data: MonthlySchedule | undefined;
  adjacentData?: MonthlySchedule[];
  isLoading: boolean;
  loadingScope?: CalendarLoadingScope | null;
  onSlotClick: (slots: ShiftSlot[]) => void;
  onDayClick: (date: string, slots: ShiftSlot[]) => void;
  selectedUnit: string | null;
  // When non-empty, the calendar shows only shifts assigned to one of these
  // employees ("Individual Schedule" view). When empty / undefined, shows the
  // full facility schedule.
  selectedEmployeeIds?: Set<string>;
  statusFilter: StatusFilter;
  today: Date;
  // When provided, the calendar renders exactly 28 days (4 rows × 7 cols)
  // starting at `period.start` (a Sunday). Every cell is in-period — there is
  // no greyed adjacent-month overflow. The component still pulls per-day data
  // from `data` and `adjacentData` since the underlying API is month-organized.
  period?: { start: Date; end: Date };
}

interface PillRow {
  label: string;
  shift: ShiftLabel;
  assigned: number;
  required: number;
  status: ShiftSlotStatus;
  slots: ShiftSlot[];
}

interface CalendarCell {
  date: Date;
  day: DaySchedule | null;
  isCurrentMonth: boolean;
}

function aggregateDayStatus(
  slots: ShiftSlot[],
  selectedUnit: string | null,
  selectedEmployeeIds?: Set<string>,
): PillRow[] {
  const isIndividualView =
    selectedEmployeeIds !== undefined && selectedEmployeeIds.size > 0;

  return SHIFT_ORDER.map(({ key, label }) => {
    let scoped = slots.filter(
      (s) => s.shift_label === key && (!selectedUnit || s.unit_id === selectedUnit),
    );

    if (isIndividualView) {
      // Keep only slots that include at least one selected employee.
      scoped = scoped.filter((s) =>
        s.assigned_employees.some((e) => selectedEmployeeIds!.has(e.employee_id)),
      );
    }

    let assigned: number;
    let required: number;
    if (isIndividualView) {
      // Individual view: count selected employees' confirmed assignments
      // and treat that count as the "required" target so a pill can render
      // green (single shift = 1/1) instead of perpetually amber.
      assigned = scoped.reduce(
        (n, s) =>
          n +
          s.assigned_employees.filter(
            (e) =>
              selectedEmployeeIds!.has(e.employee_id) &&
              e.confirmation_status === "ACCEPTED",
          ).length,
        0,
      );
      required = scoped.reduce(
        (n, s) =>
          n +
          s.assigned_employees.filter((e) =>
            selectedEmployeeIds!.has(e.employee_id),
          ).length,
        0,
      );
    } else {
      // Count only ACCEPTED invitees as real coverage. PENDING / DECLINED /
      // UNSENT shouldn't paint the pill green — they haven't confirmed the shift.
      assigned = scoped.reduce(
        (n, s) =>
          n +
          s.assigned_employees.filter(
            (e) => e.confirmation_status === "ACCEPTED",
          ).length,
        0,
      );
      required = scoped.reduce((n, s) => n + s.required_count, 0);
    }

    let status: ShiftSlotStatus;
    if (assigned === 0 && required > 0) status = "unassigned";
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

function formatDateKey(date: Date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function MonthCalendar({
  data,
  adjacentData = [],
  isLoading,
  loadingScope = null,
  onSlotClick,
  onDayClick,
  selectedUnit,
  selectedEmployeeIds,
  statusFilter,
  today,
  period,
}: MonthCalendarProps) {
  // Which pill, if any, currently owns the shared `view-transition-name`.
  // Set just before opening the detail dialog so the browser can morph the
  // pill into the dialog. Cleared once the dialog has mounted.
  const [morphingKey, setMorphingKey] = useState<string | null>(null);

  function openShiftFromPill(pillKey: string, slots: ShiftSlot[]) {
    setMorphingKey(pillKey);
    // Wait one frame so React paints the pill with the view-transition-name
    // before we ask the browser to snapshot.
    requestAnimationFrame(() => {
      withViewTransition(() => {
        onSlotClick(slots);
        setMorphingKey(null);
      });
    });
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 text-muted-foreground">
        Loading schedule...
      </div>
    );
  }

  // Merge any month payloads into a single date-keyed lookup so the 28-day
  // window can reach into adjacent months naturally.
  const daysByDate = new Map<string, DaySchedule>();
  for (const schedule of [data, ...adjacentData]) {
    if (!schedule) continue;
    for (const day of schedule.days) {
      daysByDate.set(day.date, day);
    }
  }

  const hasAnyData = daysByDate.size > 0;

  const cells: CalendarCell[] = [];
  if (period) {
    // 4-week (28-day) view: always 4 rows × 7 cols starting at period.start.
    // Every cell is in-period; we no longer dim "outside the month" days.
    for (let i = 0; i < 28; i++) {
      const date = new Date(period.start);
      date.setDate(period.start.getDate() + i);
      const key = formatDateKey(date);
      cells.push({
        date,
        day: daysByDate.get(key) ?? null,
        isCurrentMonth: true,
      });
    }
  } else {
    // Legacy month view (kept for any other callers / tests).
    if (!data || data.days.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center gap-2 h-96 text-muted-foreground motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-300">
          <CalendarOff className="h-7 w-7 motion-safe:animate-breathe" />
          <span>No schedule data for this month.</span>
        </div>
      );
    }
    const firstDate = new Date(data.days[0].date + "T00:00:00");
    const startDow = firstDate.getDay();
    const totalDays = data.days.length;
    const gridMonth = firstDate.getMonth();
    const gridYear = firstDate.getFullYear();
    for (let i = 0; i < startDow; i++) {
      const date = new Date(gridYear, gridMonth, i - startDow + 1);
      cells.push({
        date,
        day: daysByDate.get(formatDateKey(date)) ?? null,
        isCurrentMonth: false,
      });
    }
    for (let d = 0; d < totalDays; d++) {
      cells.push({
        date: new Date(data.days[d].date + "T00:00:00"),
        day: data.days[d],
        isCurrentMonth: true,
      });
    }
    while (cells.length % 7 !== 0) {
      const trailingDay = totalDays + (cells.length - startDow - totalDays) + 1;
      const date = new Date(gridYear, gridMonth, trailingDay);
      cells.push({
        date,
        day: daysByDate.get(formatDateKey(date)) ?? null,
        isCurrentMonth: false,
      });
    }
  }

  // Empty-state for the 4-week view: only render when no data has loaded yet
  // for any month covered by the period.
  if (period && !hasAnyData) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 h-96 text-muted-foreground motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-300">
        <CalendarOff className="h-7 w-7 motion-safe:animate-breathe" />
        <span>No schedule data for this period.</span>
      </div>
    );
  }

  const totalRows = cells.length / 7;
  // Loading overlay scope. For 4-week view, any non-null scope highlights the
  // entire grid (the grid IS the period, and the underlying API is monthly).
  let loadingRowStart: number | null = null;
  let loadingRowEnd: number | null = null;
  if (period) {
    if (loadingScope) {
      loadingRowStart = 1;
      loadingRowEnd = totalRows + 1;
    }
  } else if (loadingScope?.kind === "month") {
    const firstCell = cells[0]?.date;
    if (
      firstCell &&
      loadingScope.year === firstCell.getFullYear() &&
      loadingScope.month === firstCell.getMonth() + 1
    ) {
      loadingRowStart = 1;
      loadingRowEnd = totalRows + 1;
    }
  } else if (loadingScope?.kind === "week") {
    const target = loadingScope.weekStart;
    const idx = cells.findIndex((c) => formatDateKey(c.date) === target);
    if (idx >= 0) {
      const row = Math.floor(idx / 7) + 1;
      loadingRowStart = row;
      loadingRowEnd = row + 1;
    }
  }
  const isLoadingActive = loadingRowStart !== null && loadingRowEnd !== null;

  return (
    <div className="w-full relative">
      {/* Indeterminate progress bar — pinned to top of card */}
      {isLoadingActive && (
        <div
          aria-hidden
          className="pointer-events-none absolute -top-3 left-0 right-0 h-0.5 overflow-hidden rounded-full bg-sky-100"
        >
          <div
            className="h-full w-full origin-left rounded-full bg-gradient-to-r from-sky-400 via-sky-500 to-indigo-500 motion-safe:animate-indeterminate"
          />
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 pb-3 text-xs">
        {(Object.keys(STATUS_LABEL) as ShiftSlotStatus[]).map((s) => (
          <div key={s} className="flex items-center gap-1.5">
            <span className={cn("h-2.5 w-2.5 rounded-full", DOT_CLASSES[s])} />
            <span className="text-muted-foreground">{STATUS_LABEL[s]}</span>
          </div>
        ))}
      </div>

      {/* Header row — rotated so the first column matches the rotation
          start. In a 4-week period the columns are not necessarily Sun-first
          (the rotation epoch is Jan 1, 2026 which is a Thursday). */}
      <div className="grid grid-cols-7 border-b border-t">
        {(period
          ? Array.from({ length: 7 }, (_, i) =>
              WEEKDAYS[(period.start.getDay() + i) % 7],
            )
          : WEEKDAYS
        ).map((d, i) => (
          <div
            key={`${d}-${i}`}
            className="text-center text-[11px] font-semibold tracking-wider text-muted-foreground py-2"
          >
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 border-l relative">
        {cells.map((cell) => {
          const dayNum = cell.date.getDate();
          const day = cell.day;

          if (!cell.isCurrentMonth) {
            const rows = aggregateDayStatus(
              day?.slots ?? [],
              selectedUnit,
              selectedEmployeeIds,
            );
            return (
              <div
                key={`adjacent-${formatDateKey(cell.date)}`}
                className="min-h-32 border-r border-b bg-muted/10 p-1.5 flex flex-col gap-1"
              >
                <div className="flex items-center">
                  <button
                    type="button"
                    disabled
                    aria-label={`${formatDateKey(cell.date)} outside current month`}
                    className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-dashed border-slate-300 text-xs text-slate-400"
                    title="Outside current month"
                  >
                    {String(dayNum).padStart(2, "0")}
                  </button>
                </div>
                <div className="flex flex-col gap-1 opacity-60 saturate-50">
                  {rows.map((r) => {
                    const faded =
                      statusFilter !== "all" && statusFilter !== r.status;
                    const isEmpty = r.slots.length === 0;
                    if (isEmpty) {
                      return (
                        <div
                          key={r.shift}
                          className={cn(
                            "w-full flex items-center justify-between",
                            "rounded border border-dashed px-1.5 py-0.5 text-[11px] font-medium",
                            "border-slate-300 bg-slate-50 text-slate-500",
                            faded && "opacity-25",
                          )}
                          title={`${r.label} — Not scheduled`}
                        >
                          <span>{r.label}</span>
                          <span className="tabular-nums">—</span>
                        </div>
                      );
                    }
                    return (
                      <div
                        key={r.shift}
                        className={cn(
                          "w-full flex items-center justify-between",
                          "rounded border px-1.5 py-0.5 text-[11px] font-medium",
                          PILL_CLASSES[r.status],
                          faded && "opacity-25",
                        )}
                        title={`${r.label} — ${STATUS_LABEL[r.status]} (${r.assigned}/${r.required})`}
                      >
                        <span>{r.label}</span>
                        <span className="tabular-nums">
                          {r.assigned}/{r.required}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          }

          if (!day) return null;

          const cellDate = new Date(day.date + "T00:00:00");
          const isToday = isSameDay(cellDate, today);
          const rows = aggregateDayStatus(
            day.slots,
            selectedUnit,
            selectedEmployeeIds,
          );

          // Anchor month = the month containing period.start. Days outside
          // that month get a subtle tone shift so the boundary is visible
          // without dominating the cell. Day 1 of any month also gets the
          // abbreviated month name inline so the user always knows where the
          // boundary is.
          const cellMonth = cell.date.getMonth();
          const anchorMonth = period
            ? period.start.getMonth()
            : cellMonth;
          const inSecondaryMonth = cellMonth !== anchorMonth;
          const isMonthStart = dayNum === 1;
          const dayLabel = isMonthStart
            ? `${MONTH_SHORT[cellMonth]} 1`
            : String(dayNum).padStart(2, "0");
          return (
            <div
              key={day.date}
              className={cn(
                "min-h-32 border-r border-b p-1.5 flex flex-col gap-1",
                inSecondaryMonth && "bg-muted/20",
              )}
            >
              <div className="flex items-center">
                <button
                  type="button"
                  onClick={() => onDayClick(day.date, day.slots)}
                  aria-label={`${day.date} schedule`}
                  className={cn(
                    "inline-flex h-6 items-center justify-center rounded-full text-xs cursor-pointer tabular-nums",
                    "transition-all duration-200 ease-out hover:scale-110 active:scale-95",
                    isMonthStart ? "px-2 font-semibold" : "w-6",
                    isToday
                      ? "bg-blue-600 text-white font-semibold hover:bg-blue-700 ring-2 ring-blue-200 ring-offset-1"
                      : isMonthStart
                        ? "bg-slate-900 text-white hover:bg-slate-800"
                        : inSecondaryMonth
                          ? "text-muted-foreground/70 hover:bg-muted hover:text-foreground"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                  title={
                    isMonthStart
                      ? `${MONTH_SHORT[cellMonth]} 1 — start of new month`
                      : "View all shifts for this day"
                  }
                >
                  {dayLabel}
                </button>
              </div>

              <div className="flex flex-col gap-1">
                {rows.map((r) => {
                  const faded =
                    statusFilter !== "all" && statusFilter !== r.status;
                  const isEmpty = r.slots.length === 0;
                  if (isEmpty) {
                    return (
                      <div
                        key={r.shift}
                        className={cn(
                          "w-full flex items-center justify-between",
                          "rounded border border-dashed px-1.5 py-0.5 text-[11px] font-medium",
                          "border-slate-300 bg-slate-50 text-slate-500",
                          faded && "opacity-25",
                        )}
                        title={`${r.label} — Not scheduled`}
                      >
                        <span>{r.label}</span>
                        <span className="tabular-nums">—</span>
                      </div>
                    );
                  }
                  const pillKey = `${day.date}-${r.shift}`;
                  return (
                    <ShiftPill
                      key={r.shift}
                      pillKey={pillKey}
                      label={r.label}
                      assigned={r.assigned}
                      required={r.required}
                      status={r.status}
                      faded={faded}
                      isMorphing={morphingKey === pillKey}
                      onActivate={() => openShiftFromPill(pillKey, r.slots)}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Loading overlay — covers the affected row(s) only */}
        {isLoadingActive && loadingRowStart !== null && loadingRowEnd !== null && (
          <LoadingOverlay
            rowStart={loadingRowStart}
            rowEnd={loadingRowEnd}
            label={loadingScope?.label ?? ""}
          />
        )}
      </div>
    </div>
  );
}

function LoadingOverlay({
  rowStart,
  rowEnd,
  label,
}: {
  rowStart: number;
  rowEnd: number;
  label: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`Building ${label}`}
      style={{
        gridRow: `${rowStart} / ${rowEnd}`,
        gridColumn: "1 / -1",
      }}
      className={cn(
        "pointer-events-none relative z-10 overflow-hidden",
        "border-r border-b border-sky-300/60",
        "bg-white/35 backdrop-blur-[2px]",
        "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:duration-300",
      )}
    >
      {/* Diagonal sheen sweep */}
      <div
        aria-hidden
        className="absolute inset-y-0 left-0 w-1/3 -skew-x-12 motion-safe:animate-scan-sweep"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(56,189,248,0.18) 50%, transparent 100%)",
        }}
      />
      {/* Centered status pill */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="flex items-center gap-2 rounded-full border border-sky-200 bg-white/90 px-3 py-1.5 text-xs font-medium text-sky-900 shadow-sm motion-safe:animate-soft-pulse">
          <Sparkles className="h-3.5 w-3.5 text-sky-600" />
          <span>Building {label}…</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ShiftPill — one of three (Day/Evening/Night) pills inside a calendar cell.
//
// Why this is its own component:
//   1. Status crossfade — `transition-colors` only kicks in if classNames
//      change between the *same* element. Pulling out a stable pill avoids
//      remounts when status changes.
//   2. Halo on improvement — needs a ref to the previous status so we can
//      tell unassigned → fully_staffed apart from a no-op render.
//   3. View-transition morph — only the *clicked* pill should claim the
//      shared name; doing this at the cell level was awkward.
// ---------------------------------------------------------------------------

function ShiftPill({
  pillKey,
  label,
  assigned,
  required,
  status,
  faded,
  isMorphing,
  onActivate,
}: {
  pillKey: string;
  label: string;
  assigned: number;
  required: number;
  status: ShiftSlotStatus;
  faded: boolean;
  isMorphing: boolean;
  onActivate: () => void;
}) {
  // Track previous status as state (not a ref) so we can react to changes
  // during render — this avoids a setState-in-effect cascading-render warning.
  const [prevStatus, setPrevStatus] = useState(status);
  const [haloKey, setHaloKey] = useState(0);

  if (status !== prevStatus) {
    setPrevStatus(status);
    if (STATUS_RANK[status] > STATUS_RANK[prevStatus]) {
      setHaloKey((k) => k + 1);
    }
  }

  // The view-transition-name is set inline so it can be swapped on/off
  // without forcing a className recompute.
  const style = isMorphing
    ? ({ viewTransitionName: SHIFT_PILL_VT_NAME } as React.CSSProperties)
    : undefined;

  return (
    <button
      type="button"
      onClick={onActivate}
      data-pill-key={pillKey}
      data-status={status}
      style={style}
      className={cn(
        "relative w-full flex items-center justify-between",
        "rounded border px-1.5 py-0.5 text-[11px] font-medium",
        "cursor-pointer transition-[background-color,border-color,color,transform,box-shadow,filter] duration-300 ease-out",
        "hover:-translate-y-px hover:shadow-sm hover:brightness-105 active:translate-y-0",
        PILL_CLASSES[status],
        faded && "opacity-25",
      )}
      title={`${label} — ${STATUS_LABEL[status]} (${assigned}/${required})`}
    >
      {haloKey > 0 && (
        <span
          key={haloKey}
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded motion-safe:animate-flash-halo"
        />
      )}
      <span>{label}</span>
      <span className="tabular-nums">
        <NumberPop value={assigned} />/{required}
      </span>
    </button>
  );
}
