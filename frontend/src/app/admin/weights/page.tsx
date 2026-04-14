"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { useWeights, useUpdateWeights } from "@/lib/queries";
import type { ScoringWeights } from "@/lib/types";

const weightLabels: Record<string, string> = {
  overtime_headroom: "Overtime Headroom",
  proximity: "Proximity (tiebreaker)",
  clinical_fit: "Clinical Fit",
  float_penalty: "Float Penalty",
};

export default function WeightsPage() {
  const { data: weights, isLoading, isError, error } = useWeights();
  const updateMutation = useUpdateWeights();
  const [draftState, setDraft] = useState<ScoringWeights | null>(null);

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
        <h2 className="text-2xl font-bold">Scoring Weights</h2>
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

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Dimension Weights</span>
            <Badge variant={isSumValid ? "secondary" : "destructive"}>
              Sum: {weightSum.toFixed(2)}
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
          <CardTitle>Thresholds</CardTitle>
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
          <CardTitle>Clinical Fit Scores</CardTitle>
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
          <CardTitle>Float Penalty Values</CardTitle>
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
