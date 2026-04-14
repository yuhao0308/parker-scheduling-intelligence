"use client";

import { useState } from "react";
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
import { MonthCalendar } from "@/components/month-calendar";
import { ShiftDetailDialog } from "@/components/shift-detail-dialog";
import { useMonthlySchedule, useGenerateSchedule, useUnits } from "@/lib/queries";
import type { ShiftSlot } from "@/lib/types";

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

  const { data, isLoading } = useMonthlySchedule(year, month);
  const generateMutation = useGenerateSchedule();
  const { data: units } = useUnits();

  const [selectedUnit, setSelectedUnit] = useState<string | null>(null);

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else { setMonth(month - 1); }
  }

  function nextMonth() {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else { setMonth(month + 1); }
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

  // Count statuses for summary
  const statusCounts = { assigned: 0, unassigned: 0, callout: 0 };
  if (data) {
    for (const day of data.days) {
      for (const slot of day.slots) {
        statusCounts[slot.status]++;
      }
    }
  }

  return (
    <div className="w-full space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={prevMonth}>
            &larr;
          </Button>
          <h2 className="text-2xl font-bold">
            {MONTH_NAMES[month - 1]} {year}
          </h2>
          <Button variant="outline" size="sm" onClick={nextMonth}>
            &rarr;
          </Button>
        </div>
        <div className="flex items-center gap-2">
          {/* Unit filter */}
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
          <Button onClick={() => setGenerateOpen(true)}>
            Generate Schedule
          </Button>
        </div>
      </div>

      {/* Status summary */}
      {data && (
        <div className="flex items-center gap-4">
          <Badge className="bg-emerald-100 text-emerald-800" variant="secondary">
            {statusCounts.assigned} Assigned
          </Badge>
          <Badge className="bg-amber-100 text-amber-800" variant="secondary">
            {statusCounts.unassigned} Unassigned
          </Badge>
          <Badge className="bg-red-100 text-red-800" variant="secondary">
            {statusCounts.callout} Callouts
          </Badge>
        </div>
      )}

      {/* Generation result */}
      {generateMutation.isSuccess && generateMutation.data && (
        <Card>
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

      {/* Calendar */}
      <Card>
        <CardContent className="p-2">
          <MonthCalendar
            data={data}
            isLoading={isLoading}
            onSlotClick={handleSlotClick}
            selectedUnit={selectedUnit}
          />
        </CardContent>
      </Card>

      {/* Shift detail dialog */}
      <ShiftDetailDialog
        slot={activeSlot}
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
              {generateMutation.isPending ? "Generating..." : "Generate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
