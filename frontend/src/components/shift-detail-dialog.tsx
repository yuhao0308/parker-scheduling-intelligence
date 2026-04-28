"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertCircle, Loader2, RotateCcw } from "lucide-react";
import { CandidateList } from "./candidate-list";
import { OverrideDialog } from "./override-dialog";
import {
  useCalloutJob,
  useSubmitCallout,
  useSubmitOverride,
} from "@/lib/queries";
import { jobToResult } from "@/app/callout/page";
import type {
  CalloutJobResponse,
  CalloutResponse,
  ScoredCandidate,
  ShiftSlot,
  ShiftSlotStatus,
} from "@/lib/types";

interface ShiftDetailDialogProps {
  slots: ShiftSlot[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const statusBadge: Record<ShiftSlotStatus, { label: string; className: string }> = {
  fully_staffed: { label: "Fully Staffed", className: "bg-emerald-100 text-emerald-800" },
  partially_staffed: { label: "Partially Staffed", className: "bg-amber-100 text-amber-800" },
  unassigned: { label: "Unassigned", className: "bg-slate-100 text-slate-700" },
};

export function ShiftDetailDialog({
  slots,
  open,
  onOpenChange,
}: ShiftDetailDialogProps) {
  // Track the active background job id rather than caching the full
  // CalloutResponse — the page polls until it resolves.
  const [calloutId, setCalloutId] = useState<number | null>(null);
  const [overrideCandidate, setOverrideCandidate] = useState<ScoredCandidate | null>(null);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const calloutMutation = useSubmitCallout();
  const overrideMutation = useSubmitOverride();
  const jobQuery = useCalloutJob(calloutId);
  const job: CalloutJobResponse | null = jobQuery.data ?? null;
  const result: CalloutResponse | null = job ? jobToResult(job) : null;

  function handleClose(val: boolean) {
    if (!val) {
      setCalloutId(null);
      setSubmitted(false);
      setOverrideCandidate(null);
      calloutMutation.reset();
      overrideMutation.reset();
    }
    onOpenChange(val);
  }

  function handleGetRecommendations() {
    const slot = slots[0];
    if (!slot) return;
    // Use callout employee if available, otherwise first assigned employee
    const calloutEmployeeId =
      slot.callout_employee_ids?.[0] ??
      slot.assigned_employees[0]?.employee_id ??
      "CNA001"; // fallback for demo
    calloutMutation.mutate(
      {
        callout_employee_id: calloutEmployeeId,
        unit_id: slot.unit_id,
        shift_date: slot.shift_date,
        shift_label: slot.shift_label,
      },
      { onSuccess: (data) => setCalloutId(data.callout_id) },
    );
  }

  function handleRetry() {
    setCalloutId(null);
    handleGetRecommendations();
  }

  function handleSelect(candidate: ScoredCandidate) {
    if (!result) return;
    if (candidate.rank === 1) {
      overrideMutation.mutate(
        {
          recommendation_log_id: result.recommendation_log_id,
          selected_employee_id: candidate.employee_id,
          coordinator_id: "scheduler",
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
        coordinator_id: "scheduler",
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

  if (slots.length === 0) return null;

  const first = slots[0];
  const isMulti = slots.length > 1;
  const assignedAcrossUnits = slots.flatMap((s) =>
    s.assigned_employees.map((e) => ({
      ...e,
      unit_id: s.unit_id,
      unit_name: s.unit_name,
    })),
  );
  const totalRequired = slots.reduce((n, s) => n + s.required_count, 0);
  const totalConfirmed = assignedAcrossUnits.filter(
    (e) => e.confirmation_status === "ACCEPTED",
  ).length;
  const aggregatedStatus: ShiftSlotStatus = isMulti
    ? assignedAcrossUnits.length === 0 && totalRequired > 0
      ? "unassigned"
      : totalRequired > 0 && totalConfirmed >= totalRequired
        ? "fully_staffed"
        : "partially_staffed"
    : first.status;

  const badge = statusBadge[aggregatedStatus] ?? statusBadge.fully_staffed;
  const title = isMulti
    ? `All Units — ${first.shift_label} Shift`
    : `${first.unit_name} — ${first.shift_label} Shift`;

  const isJobRunning =
    job !== null && (job.status === "PENDING" || job.status === "RUNNING");
  const isJobFailed = job !== null && job.status === "FAILED";

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent
          className="sm:max-w-6xl w-[95vw] max-h-[80vh] overflow-y-auto"
          style={{ viewTransitionName: "shift-pill-active" }}
        >
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              {first.shift_date} &middot;{" "}
              <Badge className={badge.className} variant="secondary">
                {badge.label}
              </Badge>
              {isMulti && (
                <span className="ml-2 text-muted-foreground">
                  {totalConfirmed}/{totalRequired} confirmed across{" "}
                  {slots.length} units
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          {/* Assigned employees */}
          {assignedAcrossUnits.length > 0 && (
            <div className="space-y-1">
              <div className="text-sm font-medium">
                Currently Assigned ({assignedAcrossUnits.length})
              </div>
              <div className="flex flex-wrap gap-2">
                {assignedAcrossUnits.map((e) => (
                  <Badge
                    key={`${e.unit_id}-${e.employee_id}`}
                    variant="outline"
                  >
                    {e.name} ({e.license})
                    {isMulti && (
                      <span className="ml-1 text-muted-foreground">
                        · {e.unit_id}
                      </span>
                    )}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          {submitted ? (
            <div className="text-center py-6 space-y-2">
              <Badge className="bg-emerald-100 text-emerald-800 text-sm px-3 py-1">
                Replacement Logged
              </Badge>
              <p className="text-sm text-muted-foreground">
                The replacement has been recorded.
              </p>
            </div>
          ) : isJobRunning ? (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <Loader2 className="h-7 w-7 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">
                Scoring candidates…
              </p>
            </div>
          ) : isJobFailed ? (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <AlertCircle className="h-7 w-7 text-destructive" />
              <p className="text-sm text-destructive max-w-sm">
                {job?.error_message ?? "Couldn't find matches."}
              </p>
              <Button size="sm" className="gap-2" onClick={handleRetry}>
                <RotateCcw className="h-3.5 w-3.5" />
                Try Again
              </Button>
            </div>
          ) : result ? (
            <div className="space-y-3">
              <div className="text-sm font-medium">
                Suggested Fill-ins ({result.candidates.length})
              </div>
              <CandidateList
                candidates={result.candidates}
                onSelect={handleSelect}
                disabled={overrideMutation.isPending}
              />
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-4">
              {!isMulti && first.status === "unassigned" && (
                <Button
                  onClick={handleGetRecommendations}
                  disabled={calloutMutation.isPending}
                >
                  {calloutMutation.isPending
                    ? "Finding replacements..."
                    : "Get Replacement Recommendations"}
                </Button>
              )}
              {isMulti && (
                <p className="text-xs text-muted-foreground">
                  Filter to a single unit to file a callout or request
                  replacements.
                </p>
              )}
              {calloutMutation.isError && (
                <p className="text-sm text-destructive">
                  {calloutMutation.error.message}
                </p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <OverrideDialog
        candidate={overrideCandidate}
        open={overrideOpen}
        onOpenChange={setOverrideOpen}
        onConfirm={handleOverrideConfirm}
        isPending={overrideMutation.isPending}
      />
    </>
  );
}
