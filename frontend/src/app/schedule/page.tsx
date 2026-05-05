"use client";

import { useCallback, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { MonthCalendar, type StatusFilter } from "@/components/month-calendar";
import { ShiftDetailDialog } from "@/components/shift-detail-dialog";
import { DayDetailDialog } from "@/components/day-detail-dialog";
import { OperatorPanel } from "@/components/schedule/operator-panel";
import {
  useGenerateSchedule,
  useMonthlySchedule,
  useUnits,
} from "@/lib/queries";
import type { CalendarLoadingScope, MonthlySchedule, ShiftSlot } from "@/lib/types";
import {
  formatPeriodRange,
  getFourWeekSchedulePeriod,
  toDateKey,
} from "@/lib/utils";

function addMonths(year: number, month: number, delta: number) {
  const d = new Date(year, month - 1 + delta, 1);
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function isMonthlySchedule(
  schedule: MonthlySchedule | undefined,
): schedule is MonthlySchedule {
  return schedule !== undefined;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const SCENARIOS = [
  { label: "Full Staff (214)", value: undefined },
  { label: "Moderate (20)", value: 20 },
  { label: "Critical (15)", value: 15 },
];

export default function SchedulePage() {
  // Anchor date is the source of truth; the 4-week (28-day) period is derived
  // from it, and `year`/`month` are kept aligned for the existing monthly
  // schedule fetches that the calendar relies on.
  const [anchorDate, setAnchorDate] = useState<Date>(() => {
    // Default to a date that has demo data populated.
    return new Date(2026, 3, 15);
  });
  const period = useMemo(
    () => getFourWeekSchedulePeriod(anchorDate),
    [anchorDate],
  );
  const year = period.start.getFullYear();
  const month = period.start.getMonth() + 1;

  const [activeSlots, setActiveSlots] = useState<ShiftSlot[]>([]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [dayDetailOpen, setDayDetailOpen] = useState(false);
  const [activeDay, setActiveDay] = useState<{
    date: string;
    slots: ShiftSlot[];
  } | null>(null);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const [selectedUnit, setSelectedUnit] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [autogenScope, setAutogenScope] = useState<CalendarLoadingScope | null>(
    null,
  );
  const [selectedEmployeeIds, setSelectedEmployeeIds] = useState<Set<string>>(
    () => new Set(),
  );
  // Months covered by the 4-week period: anchor month, plus the month
  // containing period.end if it differs (the 28-day window may straddle a
  // month boundary).
  const endYear = period.end.getFullYear();
  const endMonth = period.end.getMonth() + 1;
  const spansTwoMonths = endYear !== year || endMonth !== month;
  const previousScope = useMemo(() => addMonths(year, month, -1), [month, year]);
  const { data, isLoading } = useMonthlySchedule(year, month);
  const { data: previousMonthData } = useMonthlySchedule(
    previousScope.year,
    previousScope.month,
  );
  const { data: nextMonthData } = useMonthlySchedule(
    spansTwoMonths ? endYear : year,
    spansTwoMonths ? endMonth : month,
  );
  const generateMutation = useGenerateSchedule();
  const { data: units } = useUnits();

  const today = useMemo(() => new Date(), []);

  function shiftPeriod(deltaDays: number) {
    setAnchorDate((prev) => {
      const next = new Date(prev);
      next.setDate(next.getDate() + deltaDays);
      return next;
    });
  }

  function goToToday() {
    setAnchorDate(new Date());
  }

  function handleAnchorDateChange(value: string) {
    if (!value) return;
    // Parse as a local date, not UTC, so the user's selected day isn't shifted.
    const [y, m, d] = value.split("-").map((n) => parseInt(n, 10));
    if (!y || !m || !d) return;
    setAnchorDate(new Date(y, m - 1, d));
  }

  function handleSlotClick(slots: ShiftSlot[]) {
    setActiveSlots(slots);
    setDetailOpen(true);
  }

  function handleDayClick(date: string, slots: ShiftSlot[]) {
    setActiveDay({ date, slots });
    setDayDetailOpen(true);
  }

  function handleOpenShiftFromDay(slots: ShiftSlot[]) {
    setDayDetailOpen(false);
    setActiveSlots(slots);
    setDetailOpen(true);
  }

  function handleGenerate() {
    const scenario = SCENARIOS[scenarioIdx];
    generateMutation.mutate(
      { year, month, staff_count_override: scenario.value },
      {
        onSuccess: () => setGenerateOpen(false),
        onError: () => {
          // Error is displayed in the dialog via generateMutation.isError
        },
      },
    );
  }

  const handleAutogenScope = useCallback(
    (scope: CalendarLoadingScope | null) => setAutogenScope(scope),
    [],
  );

  // Generate dialog uses a month-scoped mutation — surface it on the calendar
  // too so the user gets the same visual feedback regardless of entry point.
  const calendarLoadingScope: CalendarLoadingScope | null = generateMutation.isPending
    ? {
        kind: "month",
        year,
        month,
        label: `${MONTH_NAMES[month - 1]} ${year}`,
      }
    : autogenScope;

  return (
    <div className="w-full space-y-4 schedule-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 no-print">
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold">Schedule</h1>
          <p className="text-sm text-muted-foreground">
            View and manage shifts with full AI assistance
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              className="text-sm border rounded-md px-2 py-1.5 bg-background"
              value={selectedUnit ?? ""}
              onChange={(e) => setSelectedUnit(e.target.value || null)}
            >
              <option value="">All Units</option>
              {units?.map((u) => (
                <option key={u.unit_id} value={u.unit_id}>
                  {u.unit_id} — {u.name}
                </option>
              ))}
            </select>
            <select
              className="text-sm border rounded-md px-2 py-1.5 bg-background"
              value={statusFilter}
              onChange={(e) =>
                setStatusFilter(e.target.value as StatusFilter)
              }
            >
              <option value="all">Show all</option>
              <option value="fully_staffed">Fully Staffed</option>
              <option value="partially_staffed">Partially Staffed</option>
              <option value="unassigned">Unassigned</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="flex flex-col items-end mr-1">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              4-Week Schedule
            </span>
            <span className="text-base font-semibold leading-tight">
              {formatPeriodRange(period.start, period.end)}
            </span>
          </div>
          <input
            type="date"
            className="text-sm border rounded-md px-2 py-1.5 bg-background"
            value={toDateKey(anchorDate)}
            onChange={(e) => handleAnchorDateChange(e.target.value)}
            title="Pick any date — period snaps to the Sunday of that week"
          />
          <Button variant="outline" size="sm" onClick={goToToday}>
            Today
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => shiftPeriod(-28)}
            title="Previous 4-week period"
          >
            &larr;
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => shiftPeriod(28)}
            title="Next 4-week period"
          >
            &rarr;
          </Button>
          <Button
            variant="outline"
            onClick={() => window.print()}
            title="Print weekly schedule"
          >
            Print
          </Button>
          <Button onClick={() => setGenerateOpen(true)}>Generate</Button>
        </div>
      </div>

      {/* Generation result */}
      {generateMutation.isSuccess && generateMutation.data && (
        <Card className="no-print motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-top-2 motion-safe:duration-300">
          <CardContent className="py-3">
            <div className="flex items-center gap-3 text-sm">
              <Badge
                className={
                  generateMutation.data.scenario === "ideal"
                    ? "bg-emerald-100 text-emerald-800"
                    : generateMutation.data.scenario === "moderate"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-red-100 text-red-800"
                }
                variant="secondary"
              >
                {generateMutation.data.scenario.toUpperCase()}
              </Badge>
              <span>
                {generateMutation.data.entries_created} shifts scheduled
              </span>
              {generateMutation.data.unfilled_slots > 0 && (
                <span className="text-destructive">
                  {generateMutation.data.unfilled_slots} open shifts
                </span>
              )}
            </div>
            {generateMutation.data.warnings.length > 0 && (
              <details className="mt-2">
                <summary className="text-xs text-muted-foreground cursor-pointer">
                  {generateMutation.data.warnings.length} warnings
                </summary>
                <ul className="text-xs text-muted-foreground mt-1 space-y-0.5 max-h-32 overflow-y-auto">
                  {generateMutation.data.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </details>
            )}
          </CardContent>
        </Card>
      )}

      {/* Calendar + Operator side panel */}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr] schedule-grid">
        <Card className="schedule-calendar-card">
          <CardContent className="p-3">
            <MonthCalendar
              data={data}
              adjacentData={[previousMonthData, nextMonthData].filter(
                isMonthlySchedule,
              )}
              isLoading={isLoading}
              loadingScope={calendarLoadingScope}
              onSlotClick={handleSlotClick}
              onDayClick={handleDayClick}
              selectedUnit={selectedUnit}
              selectedEmployeeIds={selectedEmployeeIds}
              statusFilter={statusFilter}
              today={today}
              period={period}
            />
          </CardContent>
        </Card>

        <div className="no-print">
          <OperatorPanel
            year={year}
            month={month}
            periodStart={period.start}
            periodEnd={period.end}
            onLoadingScopeChange={handleAutogenScope}
            selectedEmployeeIds={selectedEmployeeIds}
            onSelectedEmployeeIdsChange={setSelectedEmployeeIds}
          />
        </div>
      </div>

      {/* Day detail dialog (all shifts for a date) */}
      <DayDetailDialog
        date={activeDay?.date ?? null}
        slots={activeDay?.slots ?? []}
        selectedUnit={selectedUnit}
        open={dayDetailOpen}
        onOpenChange={setDayDetailOpen}
        onOpenShift={handleOpenShiftFromDay}
      />

      {/* Shift detail dialog */}
      <ShiftDetailDialog
        slots={activeSlots}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />

      {/* Generate schedule dialog */}
      <Dialog open={generateOpen} onOpenChange={setGenerateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate Monthly Schedule</DialogTitle>
            <DialogDescription>
              Auto-generate the schedule for {MONTH_NAMES[month - 1]} {year}.
              Choose a staffing scenario for the demo.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="text-sm font-medium">Staffing Scenario</div>
            <div className="flex flex-col gap-2">
              {SCENARIOS.map((s, i) => (
                <label
                  key={i}
                  className="flex items-center gap-2 text-sm cursor-pointer"
                >
                  <input
                    type="radio"
                    name="scenario"
                    checked={scenarioIdx === i}
                    onChange={() => setScenarioIdx(i)}
                  />
                  {s.label}
                </label>
              ))}
            </div>
          </div>
          {generateMutation.isError && (
            <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-800">
              Failed to generate schedule. Make sure the backend server is running.
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setGenerateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending ? "Building..." : "Build"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
