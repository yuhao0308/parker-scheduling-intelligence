"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { CalloutForm } from "@/components/callout-form";
import { CandidateList } from "@/components/candidate-list";
import { FilterStatsBadge } from "@/components/filter-stats-badge";
import { OverrideDialog } from "@/components/override-dialog";
import { useSubmitCallout, useSubmitOverride } from "@/lib/queries";
import type { CalloutRequest, CalloutResponse, ScoredCandidate } from "@/lib/types";

export default function CalloutPage() {
  const [coordinatorId, setCoordinatorId] = useState("");
  const [result, setResult] = useState<CalloutResponse | null>(null);
  const [overrideCandidate, setOverrideCandidate] = useState<ScoredCandidate | null>(null);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const calloutMutation = useSubmitCallout();
  const overrideMutation = useSubmitOverride();

  function handleCalloutSubmit(req: CalloutRequest) {
    calloutMutation.mutate(req, {
      onSuccess: (data) => setResult(data),
    });
  }

  function handleSelect(candidate: ScoredCandidate) {
    if (!result) return;
    if (candidate.rank === 1) {
      overrideMutation.mutate(
        {
          recommendation_log_id: result.recommendation_log_id,
          selected_employee_id: candidate.employee_id,
          coordinator_id: coordinatorId || "unknown",
        },
        { onSuccess: () => setSubmitted(true) },
      );
    } else {
      setOverrideCandidate(candidate);
      setOverrideOpen(true);
    }
  }

  function handleOverrideConfirm(reason: string) {
    if (!result || !overrideCandidate) return;
    overrideMutation.mutate(
      {
        recommendation_log_id: result.recommendation_log_id,
        selected_employee_id: overrideCandidate.employee_id,
        coordinator_id: coordinatorId || "unknown",
        override_reason: reason,
      },
      {
        onSuccess: () => {
          setOverrideOpen(false);
          setSubmitted(true);
        },
      },
    );
  }

  function handleReset() {
    setResult(null);
    setSubmitted(false);
    setOverrideCandidate(null);
    calloutMutation.reset();
    overrideMutation.reset();
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Call-Out Replacement</h2>
        <div className="flex items-center gap-2">
          <Label htmlFor="coordinator" className="text-sm text-muted-foreground">
            Coordinator:
          </Label>
          <Input
            id="coordinator"
            className="w-40 h-8 text-sm"
            placeholder="Your ID"
            value={coordinatorId}
            onChange={(e) => setCoordinatorId(e.target.value)}
          />
        </div>
      </div>

      {submitted ? (
        <Card>
          <CardContent className="py-12 text-center space-y-4">
            <Badge className="bg-emerald-100 text-emerald-800 text-lg px-4 py-1">
              Selection Logged
            </Badge>
            <p className="text-muted-foreground">
              The replacement has been recorded successfully.
            </p>
            <Button onClick={handleReset}>New Call-Out</Button>
          </CardContent>
        </Card>
      ) : !result ? (
        <>
          <CalloutForm
            onSubmit={handleCalloutSubmit}
            isPending={calloutMutation.isPending}
          />
          {calloutMutation.isError && (
            <Card className="border-destructive">
              <CardContent className="py-4 text-destructive text-sm">
                {calloutMutation.error.message}
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold">
                Recommendations for {result.unit_name}
              </h3>
              <p className="text-sm text-muted-foreground">
                {result.shift_label} shift on {result.shift_date}
              </p>
            </div>
            <Button variant="outline" onClick={handleReset}>
              New Call-Out
            </Button>
          </div>

          <FilterStatsBadge stats={result.filter_stats} />

          <Card>
            <CardContent className="p-0">
              <CandidateList
                candidates={result.candidates}
                onSelect={handleSelect}
                disabled={overrideMutation.isPending}
              />
            </CardContent>
          </Card>

          {overrideMutation.isError && (
            <Card className="border-destructive">
              <CardContent className="py-4 text-destructive text-sm">
                {overrideMutation.error.message}
              </CardContent>
            </Card>
          )}

          <OverrideDialog
            candidate={overrideCandidate}
            open={overrideOpen}
            onOpenChange={setOverrideOpen}
            onConfirm={handleOverrideConfirm}
            isPending={overrideMutation.isPending}
          />
        </div>
      )}
    </div>
  );
}
