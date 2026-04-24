"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { CalloutForm } from "@/components/callout-form";
import { CandidateList } from "@/components/candidate-list";
import { FilterStatsBadge } from "@/components/filter-stats-badge";
import { OutreachConsole } from "@/components/callout/outreach-console";
import { useCalloutJob, useSendOutreach, useSubmitCallout } from "@/lib/queries";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Plus,
  RotateCcw,
  User,
  UserX,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  CalledOutEmployee,
  CalloutJobResponse,
  CalloutRequest,
  CalloutResponse,
  ScoredCandidate,
  ShiftLabel,
} from "@/lib/types";

const licenseBadgeClass: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800 border-blue-200",
  LPN: "bg-green-100 text-green-800 border-green-200",
  CNA: "bg-amber-100 text-amber-800 border-amber-200",
  PCT: "bg-purple-100 text-purple-800 border-purple-200",
};

// Separate from React Query cache: survives full page reloads and
// top-nav clicks that re-mount this route.
const ACTIVE_JOB_STORAGE_KEY = "callout:activeJobId";

function readStoredJobId(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
    if (!raw) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  } catch {
    return null;
  }
}

function writeStoredJobId(id: number | null): void {
  if (typeof window === "undefined") return;
  try {
    if (id === null) {
      window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
    } else {
      window.localStorage.setItem(ACTIVE_JOB_STORAGE_KEY, String(id));
    }
  } catch {
    // Ignore quota / privacy-mode errors — the URL is still authoritative.
  }
}

function tenureLabel(hireDate: string | null): string | null {
  if (!hireDate) return null;
  const hire = new Date(hireDate);
  if (Number.isNaN(hire.getTime())) return null;
  const years = (Date.now() - hire.getTime()) / (365.25 * 24 * 60 * 60 * 1000);
  if (years >= 1) return `${years.toFixed(1)} yr tenure`;
  const months = Math.max(0, Math.round(years * 12));
  return `${months} mo tenure`;
}

function CalledOutEmployeeCard({
  employee,
}: {
  employee: CalledOutEmployee | null | undefined;
}) {
  if (!employee) return null;
  const tenure = tenureLabel(employee.hire_date);
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50/50 shadow-sm">
      <div className="flex items-start gap-3 px-5 py-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-700">
          <UserX className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-rose-700">
              Called Out — Finding a Match For
            </p>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="text-base font-semibold">{employee.name}</span>
            <Badge
              variant="secondary"
              className={cn(
                "border text-[11px] px-1.5 py-0",
                licenseBadgeClass[employee.license] ?? "",
              )}
            >
              {employee.license}
            </Badge>
            <Badge
              variant="secondary"
              className="border text-[11px] px-1.5 py-0 bg-muted text-muted-foreground"
            >
              {employee.employment_class.replace(/_/g, " ")}
            </Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
            <span>
              Home unit:{" "}
              <span className="font-medium text-foreground">
                {employee.home_unit_name ?? employee.home_unit_id ?? "—"}
              </span>
            </span>
            {tenure && (
              <>
                <span>·</span>
                <span>{tenure}</span>
              </>
            )}
            <span>·</span>
            <span className="font-mono text-[10px]">{employee.employee_id}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

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

/* ── Finding-replacements spinner view ──────────────────────────────────── */

function FindingReplacementsView({
  job,
  onCancel,
}: {
  job: CalloutJobResponse;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">
            Finding replacements for {job.unit_name}
          </h3>
          <p className="text-sm text-muted-foreground">
            {job.shift_label} shift · {job.shift_date}
          </p>
        </div>
        <Button variant="outline" size="sm" className="shrink-0 gap-2" onClick={onCancel}>
          <Plus className="h-3.5 w-3.5" />
          New Call-Out
        </Button>
      </div>

      <CalledOutEmployeeCard employee={job.called_out_employee} />

      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border bg-card py-16 text-center shadow-sm">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <div className="space-y-1">
          <p className="text-base font-medium">Scoring candidates…</p>
          <p className="text-sm text-muted-foreground">
            You can navigate away — this page will pick up where it left off.
          </p>
        </div>
      </div>
    </div>
  );
}

/* ── Failed job view ────────────────────────────────────────────────────── */

function FailedJobView({
  job,
  onRetry,
  onReset,
}: {
  job: CalloutJobResponse;
  onRetry: () => void;
  onReset: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">
            Couldn&apos;t find replacements for {job.unit_name}
          </h3>
          <p className="text-sm text-muted-foreground">
            {job.shift_label} shift · {job.shift_date}
          </p>
        </div>
        <Button variant="outline" size="sm" className="shrink-0 gap-2" onClick={onReset}>
          <Plus className="h-3.5 w-3.5" />
          New Call-Out
        </Button>
      </div>

      <CalledOutEmployeeCard employee={job.called_out_employee} />

      <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-destructive/50 bg-destructive/5 py-12 text-center shadow-sm">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <div className="space-y-1">
          <p className="text-base font-medium text-destructive">
            Recommendation pipeline failed
          </p>
          <p className="text-sm text-muted-foreground max-w-md">
            {job.error_message ?? "An unknown error occurred."}
          </p>
        </div>
        <Button className="mt-2 gap-2" onClick={onRetry}>
          <RotateCcw className="h-4 w-4" />
          Try Again
        </Button>
      </div>
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

      <CalledOutEmployeeCard employee={result.called_out_employee} />

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

/* ── Job → legacy result projection ─────────────────────────────────────── */

export function jobToResult(job: CalloutJobResponse): CalloutResponse | null {
  if (
    job.status !== "COMPLETED" ||
    job.recommendation_log_id == null ||
    job.candidates == null ||
    job.filter_stats == null ||
    job.generated_at == null
  ) {
    return null;
  }
  return {
    callout_id: job.callout_id,
    recommendation_log_id: job.recommendation_log_id,
    unit_id: job.unit_id,
    unit_name: job.unit_name,
    shift_date: job.shift_date,
    shift_label: job.shift_label,
    called_out_employee: job.called_out_employee,
    candidates: job.candidates,
    filter_stats: job.filter_stats,
    generated_at: job.generated_at,
  };
}

/* ── Main page ──────────────────────────────────────────────────────────── */

function CalloutPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const calloutIdParam = useMemo(() => {
    const raw = searchParams.get("callout_id");
    if (!raw) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [searchParams]);

  const [calloutId, setCalloutId] = useState<number | null>(calloutIdParam);

  // Keep the internal id in sync when the URL changes underneath us
  // (e.g. browser back/forward).
  useEffect(() => {
    setCalloutId(calloutIdParam);
  }, [calloutIdParam]);

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
  const [submitted, setSubmitted] = useState(false);
  const [lastRequest, setLastRequest] = useState<CalloutRequest | null>(null);

  const calloutMutation = useSubmitCallout();
  const sendOutreachMutation = useSendOutreach();

  const setCalloutIdInUrl = useCallback(
    (id: number | null) => {
      setCalloutId(id);
      writeStoredJobId(id);

      const params = new URLSearchParams(searchParams.toString());
      if (id === null) {
        params.delete("callout_id");
      } else {
        params.set("callout_id", String(id));
      }
      const query = params.toString();
      router.replace(query ? `/callout?${query}` : "/callout", { scroll: false });
    },
    [router, searchParams],
  );

  // On mount, if the URL has no callout_id but localStorage does (e.g. the
  // user top-nav'd to Schedule and came back), hydrate from storage so
  // the polling query wakes up.
  useEffect(() => {
    if (calloutIdParam !== null) return;
    const stored = readStoredJobId();
    if (stored !== null) {
      setCalloutIdInUrl(stored);
    }
    // Mount-only hydration. Subsequent changes flow through the URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const jobQuery = useCalloutJob(calloutId);
  const job = jobQuery.data ?? null;

  // If the stored id 404s (DB wipe / staler than the server), clear it
  // so the user doesn't stare at a restoring-spinner forever.
  useEffect(() => {
    if (jobQuery.isError && calloutId !== null) {
      setCalloutIdInUrl(null);
    }
  }, [jobQuery.isError, calloutId, setCalloutIdInUrl]);

  const result = job ? jobToResult(job) : null;

  const step: 1 | 2 | 3 = submitted ? 3 : result ? 2 : 1;

  function handleCalloutSubmit(req: CalloutRequest) {
    setLastRequest(req);
    calloutMutation.mutate(req, {
      onSuccess: (data) => {
        setCalloutIdInUrl(data.callout_id);
      },
    });
  }

  function handleRetry() {
    if (!lastRequest) {
      handleReset();
      return;
    }
    // Clear the old job id first so the Restoring spinner doesn't flash.
    setCalloutIdInUrl(null);
    calloutMutation.mutate(lastRequest, {
      onSuccess: (data) => {
        setCalloutIdInUrl(data.callout_id);
      },
    });
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
    setSubmitted(false);
    setLastRequest(null);
    calloutMutation.reset();
    sendOutreachMutation.reset();
    setCalloutIdInUrl(null);
  }

  const isRestoring =
    calloutId !== null && jobQuery.isLoading && !jobQuery.data;

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
      ) : isRestoring ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border bg-card py-16 text-center shadow-sm">
          <Loader2 className="h-7 w-7 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Restoring call-out…</p>
        </div>
      ) : job && (job.status === "PENDING" || job.status === "RUNNING") ? (
        <FindingReplacementsView job={job} onCancel={handleReset} />
      ) : job && job.status === "FAILED" ? (
        <FailedJobView job={job} onRetry={handleRetry} onReset={handleReset} />
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
