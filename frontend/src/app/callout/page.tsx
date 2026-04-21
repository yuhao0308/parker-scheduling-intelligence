"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { CalloutForm } from "@/components/callout-form";
import { CandidateList } from "@/components/candidate-list";
import { FilterStatsBadge } from "@/components/filter-stats-badge";
import { OutreachConsole } from "@/components/callout/outreach-console";
import { useSendOutreach, useSubmitCallout } from "@/lib/queries";
import type {
  CalloutRequest,
  CalloutResponse,
  ScoredCandidate,
  ShiftLabel,
} from "@/lib/types";

const VALID_SHIFTS: readonly ShiftLabel[] = ["DAY", "EVENING", "NIGHT"];

export default function CalloutPage() {
  // useSearchParams requires a Suspense boundary under Next's async routing.
  return (
    <Suspense fallback={null}>
      <CalloutPageInner />
    </Suspense>
  );
}

function CalloutPageInner() {
  const searchParams = useSearchParams();

  // Prefill values from deep-link query: date / unit_id / shift / employee_id.
  const initialValues = useMemo(() => {
    const date = searchParams.get("date") ?? undefined;
    const unit_id = searchParams.get("unit_id") ?? undefined;
    const shiftRaw = searchParams.get("shift") ?? undefined;
    const shift_label = VALID_SHIFTS.includes(shiftRaw as ShiftLabel)
      ? (shiftRaw as ShiftLabel)
      : undefined;
    const employee_id = searchParams.get("employee_id") ?? undefined;
    return {
      shift_date: date,
      unit_id,
      shift_label,
      employee_id,
    };
  }, [searchParams]);

  const [coordinatorId, setCoordinatorId] = useState("");
  const [result, setResult] = useState<CalloutResponse | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const calloutMutation = useSubmitCallout();
  const sendOutreachMutation = useSendOutreach();

  function handleCalloutSubmit(req: CalloutRequest) {
    calloutMutation.mutate(req, {
      onSuccess: (data) => setResult(data),
    });
  }

  function handleSelect(candidate: ScoredCandidate) {
    // Selecting a candidate now triggers simulated SMS outreach rather than
    // immediately logging an override. The OutreachConsole below drives
    // accept/decline/timeout from there.
    if (!result) return;
    sendOutreachMutation.mutate({
      calloutId: result.callout_id,
      req: {
        recommendation_log_id: result.recommendation_log_id,
        candidate_employee_id: candidate.employee_id,
        rank: candidate.rank,
      },
    });
  }

  function handleReset() {
    setResult(null);
    setSubmitted(false);
    calloutMutation.reset();
    sendOutreachMutation.reset();
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
            initialValues={initialValues}
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
                disabled={sendOutreachMutation.isPending}
              />
            </CardContent>
          </Card>

          <OutreachConsole
            result={result}
            onAccepted={() => setSubmitted(true)}
          />

          {sendOutreachMutation.isError && (
            <Card className="border-destructive">
              <CardContent className="py-4 text-destructive text-sm">
                {(sendOutreachMutation.error as Error)?.message ?? "Outreach failed."}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
