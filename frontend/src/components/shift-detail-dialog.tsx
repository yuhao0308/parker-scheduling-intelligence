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
import { CandidateList } from "./candidate-list";
import { OverrideDialog } from "./override-dialog";
import { useSubmitCallout, useSubmitOverride } from "@/lib/queries";
import type { CalloutResponse, ShiftSlot, ScoredCandidate } from "@/lib/types";

interface ShiftDetailDialogProps {
  slot: ShiftSlot | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const statusBadge: Record<string, { label: string; className: string }> = {
  fully_staffed: { label: "Fully Staffed", className: "bg-emerald-100 text-emerald-800" },
  partially_staffed: { label: "Partially Staffed", className: "bg-amber-100 text-amber-800" },
  unassigned: { label: "Unassigned", className: "bg-slate-100 text-slate-700" },
  callout: { label: "Has Call-out", className: "bg-red-100 text-red-800" },
};

export function ShiftDetailDialog({
  slot,
  open,
  onOpenChange,
}: ShiftDetailDialogProps) {
  const [result, setResult] = useState<CalloutResponse | null>(null);
  const [overrideCandidate, setOverrideCandidate] = useState<ScoredCandidate | null>(null);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const calloutMutation = useSubmitCallout();
  const overrideMutation = useSubmitOverride();

  function handleClose(val: boolean) {
    if (!val) {
      setResult(null);
      setSubmitted(false);
      setOverrideCandidate(null);
      calloutMutation.reset();
      overrideMutation.reset();
    }
    onOpenChange(val);
  }

  function handleGetRecommendations() {
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
      { onSuccess: (data) => setResult(data) },
    );
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

  if (!slot) return null;

  const badge = statusBadge[slot.status] ?? statusBadge.fully_staffed;

  return (
    <>
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-6xl w-[95vw] max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {slot.unit_name} — {slot.shift_label} Shift
            </DialogTitle>
            <DialogDescription>
              {slot.shift_date} &middot;{" "}
              <Badge className={badge.className} variant="secondary">
                {badge.label}
              </Badge>
            </DialogDescription>
          </DialogHeader>

          {/* Assigned employees */}
          {slot.assigned_employees.length > 0 && (
            <div className="space-y-1">
              <div className="text-sm font-medium">Currently Assigned</div>
              <div className="flex flex-wrap gap-2">
                {slot.assigned_employees.map((e) => (
                  <Badge key={e.employee_id} variant="outline">
                    {e.name} ({e.license})
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
          ) : result ? (
            <div className="space-y-3">
              <div className="text-sm font-medium">
                Recommended Replacements ({result.candidates.length})
              </div>
              <CandidateList
                candidates={result.candidates}
                onSelect={handleSelect}
                disabled={overrideMutation.isPending}
              />
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-4">
              {(slot.status === "callout" || slot.status === "unassigned") && (
                <Button
                  onClick={handleGetRecommendations}
                  disabled={calloutMutation.isPending}
                >
                  {calloutMutation.isPending
                    ? "Finding replacements..."
                    : "Get Replacement Recommendations"}
                </Button>
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
