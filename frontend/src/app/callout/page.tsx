"use client";

import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CalloutForm } from "@/components/callout-form";
import { CandidateList } from "@/components/candidate-list";
import { FilterStatsBadge } from "@/components/filter-stats-badge";
import { OutreachConsole } from "@/components/callout/outreach-console";
import { useSendOutreach, useSubmitCallout } from "@/lib/queries";
import {
  AlertCircle,
  CheckCircle2,
  Plus,
  User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  CalloutRequest,
  CalloutResponse,
  ScoredCandidate,
  ShiftLabel,
} from "@/lib/types";

const VALID_SHIFTS: readonly ShiftLabel[] = ["DAY", "EVENING", "NIGHT"];

export default function CalloutPage() {
  return (
    <Suspense fallback={null}>
      <CalloutPageInner />
    </Suspense>
  );
}

/* ── Step indicator ─────────────────────────────────────────────────────── */

const STEPS = [
  { n: 1, label: "Report Call-Out" },
  { n: 2, label: "Select Replacement" },
  { n: 3, label: "Confirmed" },
] as const;

function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  return (
    <div className="flex items-center gap-1">
      {STEPS.map((s, i) => (
        <div key={s.n} className="flex items-center">
          <div
            className={cn(
              "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-all",
              step === s.n
                ? "bg-primary text-primary-foreground"
                : step > s.n
                  ? "text-emerald-600"
                  : "text-muted-foreground",
            )}
          >
            {step > s.n ? (
              <CheckCircle2 className="h-4 w-4 shrink-0" />
            ) : (
              <span
                className={cn(
                  "flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold",
                  step === s.n ? "bg-primary-foreground/20" : "bg-muted",
                )}
              >
                {s.n}
              </span>
            )}
            <span className="hidden sm:block">{s.label}</span>
          </div>
          {i < STEPS.length - 1 && (
            <div
              className={cn(
                "mx-1 h-px w-8 transition-all",
                step > s.n ? "bg-emerald-400" : "bg-muted",
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Success card ───────────────────────────────────────────────────────── */

function SuccessCard({
  onReset,
  unitName,
  shiftLabel,
  shiftDate,
}: {
  onReset: () => void;
  unitName?: string;
  shiftLabel?: string;
  shiftDate?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border bg-card py-16 text-center shadow-sm gap-4">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
        <CheckCircle2 className="h-8 w-8 text-emerald-600" />
      </div>
      <div className="space-y-1">
        <h3 className="text-xl font-semibold">Replacement Confirmed</h3>
        {unitName && shiftLabel && shiftDate && (
          <p className="text-sm text-muted-foreground">
            {unitName} · {shiftLabel} shift on {shiftDate}
          </p>
        )}
        <p className="text-sm text-muted-foreground">
          The assignment has been recorded successfully.
        </p>
      </div>
      <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200 px-4 py-1.5 text-sm font-semibold">
        Selection Logged
      </Badge>
      <Button
        variant="outline"
        className="mt-2 gap-2"
        onClick={onReset}
      >
        <Plus className="h-4 w-4" />
        New Call-Out
      </Button>
    </div>
  );
}

/* ── Results view ───────────────────────────────────────────────────────── */

interface ResultsViewProps {
  result: CalloutResponse;
  onSelect: (candidate: ScoredCandidate) => void;
  onReset: () => void;
  onAccepted: () => void;
  sendPending: boolean;
  sendError?: string;
}

function ResultsView({
  result,
  onSelect,
  onReset,
  onAccepted,
  sendPending,
  sendError,
}: ResultsViewProps) {
  return (
    <div className="space-y-4">
      {/* Sub-header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">
            Replacements for {result.unit_name}
          </h3>
          <p className="text-sm text-muted-foreground">
            {result.shift_label} shift · {result.shift_date}
          </p>
        </div>
        <Button variant="outline" size="sm" className="shrink-0 gap-2" onClick={onReset}>
          <Plus className="h-3.5 w-3.5" />
          New Call-Out
        </Button>
      </div>

      <FilterStatsBadge stats={result.filter_stats} />

      {/* Two-column layout: candidates left, outreach right */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
        {/* Candidates */}
        <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
          <div className="border-b bg-muted/40 px-5 py-4">
            <h4 className="text-sm font-semibold">Ranked Candidates</h4>
            <p className="text-xs text-muted-foreground mt-0.5">
              Grouped by similarity to the top recommendation. Click{" "}
              <strong>Contact</strong> to initiate outreach.
            </p>
          </div>
          <div className="p-5">
            <CandidateList
              candidates={result.candidates}
              onSelect={onSelect}
              disabled={sendPending}
            />
          </div>
        </div>

        {/* Outreach console */}
        <div className="lg:sticky lg:top-4 lg:self-start">
          <OutreachConsole
            result={result}
            onAccepted={() => onAccepted()}
          />
        </div>
      </div>

      {sendError && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {sendError}
        </div>
      )}
    </div>
  );
}

/* ── Main page ──────────────────────────────────────────────────────────── */

function CalloutPageInner() {
  const searchParams = useSearchParams();

  const initialValues = useMemo(() => {
    const date = searchParams.get("date") ?? undefined;
    const unit_id = searchParams.get("unit_id") ?? undefined;
    const shiftRaw = searchParams.get("shift") ?? undefined;
    const shift_label = VALID_SHIFTS.includes(shiftRaw as ShiftLabel)
      ? (shiftRaw as ShiftLabel)
      : undefined;
    const employee_id = searchParams.get("employee_id") ?? undefined;
    return { shift_date: date, unit_id, shift_label, employee_id };
  }, [searchParams]);

  const [coordinatorId, setCoordinatorId] = useState("");
  const [result, setResult] = useState<CalloutResponse | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const calloutMutation = useSubmitCallout();
  const sendOutreachMutation = useSendOutreach();

  const step: 1 | 2 | 3 = submitted ? 3 : result ? 2 : 1;

  function handleCalloutSubmit(req: CalloutRequest) {
    calloutMutation.mutate(req, { onSuccess: (data) => setResult(data) });
  }

  function handleSelect(candidate: ScoredCandidate) {
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
    <div className="max-w-5xl space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Call-Out Replacement
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Find and contact the best available replacement for a same-day call-out.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <User className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="coordinator"
              className="h-8 w-36 pl-7 text-sm"
              placeholder="Coordinator ID"
              value={coordinatorId}
              onChange={(e) => setCoordinatorId(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Step indicator */}
      <StepIndicator step={step} />

      {/* Content */}
      {submitted ? (
        <SuccessCard
          onReset={handleReset}
          unitName={result?.unit_name}
          shiftLabel={result?.shift_label}
          shiftDate={result?.shift_date}
        />
      ) : !result ? (
        <>
          <CalloutForm
            onSubmit={handleCalloutSubmit}
            isPending={calloutMutation.isPending}
            initialValues={initialValues}
          />
          {calloutMutation.isError && (
            <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {calloutMutation.error.message}
            </div>
          )}
        </>
      ) : (
        <ResultsView
          result={result}
          onSelect={handleSelect}
          onReset={handleReset}
          onAccepted={() => setSubmitted(true)}
          sendPending={sendOutreachMutation.isPending}
          sendError={
            sendOutreachMutation.isError
              ? ((sendOutreachMutation.error as Error)?.message ??
                  "Outreach failed.")
              : undefined
          }
        />
      )}
    </div>
  );
}
