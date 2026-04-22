"use client";

import { useEffect, useMemo, useState } from "react";
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
import { OperatorPanel } from "@/components/schedule/operator-panel";
import { ReplacementDialog } from "@/components/schedule/replacement-dialog";
import {
  useGenerateSchedule,
  useMonthlySchedule,
  useUnits,
} from "@/lib/queries";
import type {
  CalloutResponse,
  ConfirmationEntry,
  ShiftSlot,
} from "@/lib/types";
import { useWorkHoursMonitor } from "@/providers/work-hours-provider";

function defaultWeekStart(today = new Date()): string {
  const d = new Date(today);
  d.setHours(0, 0, 0, 0);
  const dow = d.getDay();
  const diffToMonday = (dow + 6) % 7;
  d.setDate(d.getDate() - diffToMonday);
  return d.toISOString().slice(0, 10);
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const SCENARIOS = [
  { label: "Full Staff (26)", value: undefined },
  { label: "Moderate (20)", value: 20 },
  { label: "Critical (15)", value: 15 },
];

export default function SchedulePage() {
  const [year, setYear] = useState(2026);
  const [month, setMonth] = useState(4);
  const [activeSlot, setActiveSlot] = useState<ShiftSlot | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [scenarioIdx, setScenarioIdx] = useState(0);
  const [weekStart, setWeekStart] = useState(() => defaultWeekStart());
  const [replacementEntry, setReplacementEntry] =
    useState<ConfirmationEntry | null>(null);
  const [replacementData, setReplacementData] =
    useState<CalloutResponse | null>(null);
  const [selectedUnit, setSelectedUnit] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const { setScope } = useWorkHoursMonitor();

  const { data, isLoading } = useMonthlySchedule(year, month);
  const generateMutation = useGenerateSchedule();
  const { data: units } = useUnits();

  const today = useMemo(() => new Date(), []);

  function prevMonth() {
    if (month === 1) {
      setMonth(12);
      setYear(year - 1);
    } else {
      setMonth(month - 1);
    }
  }

  function nextMonth() {
    if (month === 12) {
      setMonth(1);
      setYear(year + 1);
    } else {
      setMonth(month + 1);
    }
  }

  function goToToday() {
    const d = new Date();
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
  }

  function handleSlotClick(slot: ShiftSlot) {
    setActiveSlot(slot);
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

  useEffect(() => {
    setScope({ year, month });
  }, [month, year, setScope]);

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
              <option value="callout">Has Call-out</option>
              <option value="unassigned">Unassigned</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={goToToday}>
            Today
          </Button>
          <Button variant="outline" size="sm" onClick={prevMonth}>
            &larr;
          </Button>
          <span className="min-w-32 text-center text-lg font-semibold">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <Button variant="outline" size="sm" onClick={nextMonth}>
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
        <Card className="no-print">
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
                  {generateMutation.data.unfilled_slots} unfilled slots
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
              isLoading={isLoading}
              onSlotClick={handleSlotClick}
              selectedUnit={selectedUnit}
              statusFilter={statusFilter}
              today={today}
            />
          </CardContent>
        </Card>

        <div className="no-print">
          <OperatorPanel
            year={year}
            month={month}
            weekStart={weekStart}
            onWeekStartChange={setWeekStart}
            onDeclineReplacement={(entry, replacement) => {
              setReplacementEntry(entry);
              setReplacementData(replacement);
            }}
          />
        </div>
      </div>

      {/* Shift detail dialog */}
      <ShiftDetailDialog
        slot={activeSlot}
        open={detailOpen}
        onOpenChange={setDetailOpen}
      />

      {/* Replacement dialog */}
      <ReplacementDialog
        open={!!replacementEntry && !!replacementData}
        onOpenChange={(o) => {
          if (!o) {
            setReplacementEntry(null);
            setReplacementData(null);
          }
        }}
        entry={replacementEntry}
        replacement={replacementData}
        weekStart={weekStart}
        onReplaced={() => {
          setReplacementEntry(null);
          setReplacementData(null);
        }}
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
              {generateMutation.isPending ? "Generating..." : "Generate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
