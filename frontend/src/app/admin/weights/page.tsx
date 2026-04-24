"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { useWeights, useUpdateWeights, useResetCalendar } from "@/lib/queries";
import type { ScoringWeights } from "@/lib/types";

const weightLabels: Record<string, string> = {
  overtime_headroom: "Hours Left",
  proximity: "Distance",
  clinical_fit: "Unit Match",
  float_penalty: "Home Unit",
};

export default function WeightsPage() {
  const { data: weights, isLoading, isError, error } = useWeights();
  const updateMutation = useUpdateWeights();
  const resetCalendarMutation = useResetCalendar();
  const [draftState, setDraft] = useState<ScoringWeights | null>(null);

  function handleResetCalendar() {
    if (resetCalendarMutation.isPending) return;
    if (
      !window.confirm(
        "Demo reset: delete every scheduled shift, call-out, and invite? The calendar will be empty until you re-run Auto-Fill.",
      )
    )
      return;
    resetCalendarMutation.mutate();
  }

  if (isLoading) return <div className="p-8 text-muted-foreground">Loading weights...</div>;
  if (isError) return <div className="p-8 text-destructive">{error.message}</div>;
  const draft = draftState ?? (weights ? structuredClone(weights) : null);
  if (!draft) return null;

  const weightSum = Object.values(draft.weights).reduce((a, b) => a + b, 0);
  const isSumValid = Math.abs(weightSum - 1.0) < 0.01;

  function handleWeightChange(key: string, value: number) {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        weights: { ...prev.weights, [key]: value },
      };
    });
  }

  function handleThresholdChange(key: string, value: number) {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        thresholds: { ...prev.thresholds, [key]: value },
      };
    });
  }

  function handleClinicalChange(key: string, value: number) {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        clinical_fit_scores: { ...prev.clinical_fit_scores, [key]: value },
      };
    });
  }

  function handleFloatChange(key: string, value: number) {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        float_penalty_values: { ...prev.float_penalty_values, [key]: value },
      };
    });
  }

  function handleSave() {
    if (!draft) return;
    updateMutation.mutate(draft);
  }

  function handleReset() {
    setDraft(null);
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Matching Priorities</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleReset}>
            Reset
          </Button>
          <Button onClick={handleSave} disabled={!isSumValid || updateMutation.isPending}>
            {updateMutation.isPending ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>

      {updateMutation.isSuccess && (
        <Badge className="bg-emerald-100 text-emerald-800">Saved successfully</Badge>
      )}

      <Card className="border-dashed border-amber-300 bg-amber-50/40">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <Badge className="bg-amber-200 text-amber-900">Demo only</Badge>
              <span>Clear calendar</span>
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4">
          <div className="text-sm text-muted-foreground">
            Wipe every scheduled shift, call-out, and invite so the month starts
            empty. Use this before a fresh Auto-Fill walkthrough on the Schedule
            page.
          </div>
          <div className="flex flex-col items-end gap-1">
            <Button
              variant="outline"
              className="border-amber-400 text-amber-900 hover:bg-amber-100"
              onClick={handleResetCalendar}
              disabled={resetCalendarMutation.isPending}
            >
              {resetCalendarMutation.isPending
                ? "Resetting..."
                : "Clear calendar"}
            </Button>
            {resetCalendarMutation.isSuccess && (
              <span className="text-[11px] text-emerald-700">
                Cleared {resetCalendarMutation.data.entries_deleted} shift
                {resetCalendarMutation.data.entries_deleted === 1 ? "" : "s"}.
              </span>
            )}
            {resetCalendarMutation.isError && (
              <span className="text-[11px] text-destructive">
                {resetCalendarMutation.error.message}
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>How Much Each Factor Counts</span>
            <Badge variant={isSumValid ? "secondary" : "destructive"}>
              Total: {weightSum.toFixed(2)}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {Object.entries(draft.weights).map(([key, value]) => (
            <div key={key} className="space-y-1">
              <div className="flex justify-between text-sm">
                <Label>{weightLabels[key] ?? key}</Label>
                <span className="tabular-nums font-mono text-muted-foreground">
                  {value.toFixed(2)}
                </span>
              </div>
              <Slider
                value={[value]}
                onValueChange={(nextValue) => {
                  const sliderValue = Array.isArray(nextValue)
                    ? (nextValue[0] ?? value)
                    : nextValue;
                  handleWeightChange(key, Math.round(sliderValue * 100) / 100);
                }}
                min={0}
                max={1}
                step={0.01}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rules &amp; Limits</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(draft.thresholds).map(([key, value]) => (
            <div key={key} className="flex items-center gap-4">
              <Label className="w-56 text-sm">{key.replace(/_/g, " ")}</Label>
              <Input
                type="number"
                className="w-32"
                value={value}
                onChange={(e) =>
                  handleThresholdChange(key, parseFloat(e.target.value) || 0)
                }
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Unit Match Scores</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(draft.clinical_fit_scores).map(([key, value]) => (
            <div key={key} className="flex items-center gap-4">
              <Label className="w-56 text-sm">{key.replace(/_/g, " ")}</Label>
              <Input
                type="number"
                className="w-32"
                step={0.1}
                min={0}
                max={1}
                value={value}
                onChange={(e) =>
                  handleClinicalChange(key, parseFloat(e.target.value) || 0)
                }
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Home Unit Preference Values</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(draft.float_penalty_values).map(([key, value]) => (
            <div key={key} className="flex items-center gap-4">
              <Label className="w-56 text-sm">{key.replace(/_/g, " ")}</Label>
              <Input
                type="number"
                className="w-32"
                step={0.1}
                value={value}
                onChange={(e) =>
                  handleFloatChange(key, parseFloat(e.target.value) || 0)
                }
              />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
