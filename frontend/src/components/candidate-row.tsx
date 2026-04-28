"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScoreBreakdown } from "./score-breakdown";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  Loader2,
  Send,
  ShieldAlert,
  Star,
} from "lucide-react";
import { useWeights } from "@/lib/queries";
import type { RationaleTone, ScoredCandidate } from "@/lib/types";

const STANDARD_HOURS_REMAINING_AMBER_DEFAULT = 8.0;
const RN_SHIFTS_REMAINING_AMBER_DEFAULT = 2;
const RN_BIWEEKLY_OT_THRESHOLD = 10;
const STANDARD_WEEKLY_OT_THRESHOLD_HOURS = 37.5;

type OtBadgeState =
  | { kind: "trigger"; label: string }
  | { kind: "approaching"; label: string }
  | null;

function computeOtBadge(
  candidate: ScoredCandidate,
  thresholds: { standardHoursAmber: number; rnShiftsAmber: number },
): OtBadgeState {
  if (candidate.would_trigger_ot) {
    return { kind: "trigger", label: candidate.ot_headroom_label };
  }
  if (candidate.license === "RN") {
    const shiftsRemaining = Math.max(
      0,
      RN_BIWEEKLY_OT_THRESHOLD - candidate.shift_count_this_biweek,
    );
    if (shiftsRemaining < thresholds.rnShiftsAmber) {
      return { kind: "approaching", label: candidate.ot_headroom_label };
    }
  } else {
    const hoursRemaining = Math.max(
      0,
      STANDARD_WEEKLY_OT_THRESHOLD_HOURS - candidate.hours_this_cycle,
    );
    if (hoursRemaining < thresholds.standardHoursAmber) {
      return { kind: "approaching", label: candidate.ot_headroom_label };
    }
  }
  return null;
}

const licenseBadgeClass: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800 border-blue-200",
  LPN: "bg-green-100 text-green-800 border-green-200",
  CNA: "bg-amber-100 text-amber-800 border-amber-200",
  PCT: "bg-purple-100 text-purple-800 border-purple-200",
};

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-700";
  if (score >= 60) return "text-amber-700";
  return "text-slate-500";
}

export type CandidateRowSubmitState = "idle" | "sending" | "sent";

interface CandidateRowProps {
  candidate: ScoredCandidate;
  onSelect: (candidate: ScoredCandidate) => void;
  disabled: boolean;
  isTop?: boolean;
  submitState?: CandidateRowSubmitState;
}

export function CandidateRow({
  candidate,
  onSelect,
  disabled,
  isTop,
  submitState = "idle",
}: CandidateRowProps) {
  const [expanded, setExpanded] = useState(false);
  const scoreInt = Math.round(candidate.score * 100);
  const weights = useWeights().data;
  const otBadge = computeOtBadge(candidate, {
    standardHoursAmber:
      weights?.ot_warning_thresholds?.standard_hours_remaining_amber ??
      STANDARD_HOURS_REMAINING_AMBER_DEFAULT,
    rnShiftsAmber:
      weights?.ot_warning_thresholds?.rn_shifts_remaining_amber ??
      RN_SHIFTS_REMAINING_AMBER_DEFAULT,
  });

  const isSending = submitState === "sending";
  const isSent = submitState === "sent";

  return (
    <div
      data-submit-state={submitState}
      className={cn(
        "relative overflow-hidden rounded-lg border hover-lift transition-colors duration-300",
        isTop && !isSent
          ? "border-blue-200 bg-blue-50/40 shadow-sm shadow-blue-500/5"
          : "bg-card hover:bg-muted/30 hover:border-muted-foreground/20",
        isSent && "border-emerald-300 bg-emerald-50/60",
        // The sweep itself is keyed off this class — adding it triggers the
        // ::after pseudo to play exactly once per state change.
        isSending && "contact-sweep",
      )}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Rank badge */}
        <div className="shrink-0">
          <span
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold",
              isTop
                ? "bg-blue-600 text-white"
                : "bg-muted text-muted-foreground",
            )}
          >
            {candidate.rank}
          </span>
        </div>

        {/* Name + meta */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold">{candidate.name}</span>
            <Badge
              variant="secondary"
              className={cn(
                "border text-[11px] px-1.5 py-0",
                licenseBadgeClass[candidate.license] ?? "",
              )}
            >
              {candidate.license}
            </Badge>
            {isTop && (
              <Badge className="gap-1 text-[11px] px-1.5 py-0 bg-blue-100 text-blue-800 border border-blue-200 font-semibold">
                <Star className="h-2.5 w-2.5 fill-current motion-safe:animate-soft-pulse" />
                Best Match
              </Badge>
            )}
            {otBadge && (
              <Badge
                title={otBadge.label}
                className={cn(
                  "gap-1 text-[11px] px-1.5 py-0 border font-semibold",
                  otBadge.kind === "trigger"
                    ? "bg-red-100 text-red-800 border-red-200 motion-safe:animate-risk-pulse"
                    : "bg-amber-100 text-amber-800 border-amber-200",
                )}
              >
                <AlertTriangle className="h-2.5 w-2.5" />
                {otBadge.kind === "trigger"
                  ? "Would trigger OT"
                  : "Approaching OT"}
              </Badge>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
            <span>{candidate.employment_class.replace(/_/g, " ")}</span>
            <span>·</span>
            <span>{candidate.home_unit}</span>
            <span>·</span>
            <span className="font-mono text-[10px]">{candidate.employee_id}</span>
          </div>
        </div>

        {/* Score breakdown bars (hidden on small screens) */}
        <div className="hidden lg:block shrink-0 w-44">
          <ScoreBreakdown breakdown={candidate.score_breakdown} />
        </div>

        {/* Numeric score */}
        <div className="shrink-0 text-right w-14">
          <span
            className={cn(
              "text-2xl font-bold tabular-nums leading-none",
              scoreColor(scoreInt),
            )}
          >
            {scoreInt}
          </span>
          <div className="text-[10px] text-muted-foreground leading-none mt-0.5">
            / 100
          </div>
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "Hide why" : "Show why"}
          >
            <ChevronDown
              className={cn(
                "h-4 w-4 transition-transform duration-200",
                expanded && "rotate-180",
              )}
            />
          </Button>
          <Button
            size="sm"
            onClick={() => onSelect(candidate)}
            disabled={disabled || isSending || isSent}
            className={cn(
              "h-8 gap-1.5 px-3 text-xs transition-colors duration-300",
              isSent && "bg-emerald-600 text-white hover:bg-emerald-600",
            )}
          >
            {isSending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : isSent ? (
              <Check className="h-3 w-3 motion-safe:animate-pop" />
            ) : (
              <Send className="h-3 w-3" />
            )}
            {isSending ? "Sending" : isSent ? "Contacted" : "Contact"}
          </Button>
        </div>
      </div>

      {/* Rationale panel — smooth expand via grid-rows 0fr→1fr trick */}
      <div
        className="collapsible-row"
        data-open={expanded}
        aria-hidden={!expanded}
      >
        <div>
          <RationalePanel candidate={candidate} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rationale panel — single source of truth per concept
//
// Design principles (after a redesign pass):
//   1. Workload (this month + peak load + OT headroom) collapses into ONE
//      horizontal bar chart with a threshold marker. The bar's color is the
//      OT-risk indicator; the captions carry the numbers.
//   2. Clinical fit + float status collapse into ONE fit line.
//   3. Distance + tenure are inline meta, not full chips.
//   4. The narrative ("Why this match" / "Watch-outs") is reserved for
//      context the chart can't show — never repeats numbers.
// ---------------------------------------------------------------------------

const TYPOLOGY_LABEL: Record<string, string> = {
  LT: "Long-Term",
  SUBACUTE: "Short-Term",
};

function typologyLabel(t: string | null | undefined): string {
  if (!t) return "";
  return TYPOLOGY_LABEL[t] ?? t;
}

type WorkloadView = {
  // Inputs to the bar chart — the ACTIVE pay cycle that contains the target
  // shift. This is the number `calculate_ot_headroom` actually scores against,
  // so the chart, the score breakdown, and `would_trigger_ot` all agree.
  current: number;
  threshold: number;
  cap: number;
  // Captions
  primary: string;
  secondary: string;
  monthTotal: string;
  peakNote: string | null; // shown only when peak biweek/week > current cycle
  tone: RationaleTone;
};

const RN_BIWEEKLY_OT_SHIFTS = 10;
const RN_HIGH_OT_SHIFTS = 12;
const WEEKLY_OT_HOURS = 37.5;
const HIGH_OT_HOURS = 62.5;

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v));
}

function computeWorkload(c: ScoredCandidate): WorkloadView {
  const isRN = c.license === "RN";
  const monthTotal = c.scheduled_shifts_this_month
    ? `${c.scheduled_shifts_this_month} shifts · ${c.scheduled_hours_this_month.toFixed(1)}h scheduled this month`
    : "No shifts scheduled this month";

  if (isRN) {
    const current = c.shift_count_this_biweek;
    const threshold = RN_BIWEEKLY_OT_SHIFTS;
    const cap = RN_HIGH_OT_SHIFTS;
    const afterShift = current + 1;
    const tone: RationaleTone = c.would_trigger_ot
      ? "danger"
      : afterShift > threshold
      ? "danger"
      : afterShift === threshold
      ? "warning"
      : afterShift >= threshold - 1
      ? "neutral"
      : "positive";
    const primary = `${current} / ${threshold} shifts in this pay cycle`;
    const headroom = threshold - afterShift;
    const secondary = c.would_trigger_ot
      ? "One more shift would trigger overtime"
      : headroom > 0
      ? `${headroom} shift${headroom === 1 ? "" : "s"} of headroom after this one`
      : "This shift fits — next one would trigger OT";
    const peakNote =
      c.peak_biweekly_shifts > current
        ? `Peaks at ${c.peak_biweekly_shifts} shifts in another biweek this month`
        : null;
    return { current, threshold, cap, primary, secondary, monthTotal, peakNote, tone };
  }

  const current = c.hours_this_cycle;
  const threshold = WEEKLY_OT_HOURS;
  const cap = HIGH_OT_HOURS;
  const SHIFT_HOURS = 7.5;
  const afterShift = current + SHIFT_HOURS;
  const tone: RationaleTone = c.would_trigger_ot
    ? "danger"
    : afterShift > threshold
    ? "danger"
    : afterShift > threshold - 4
    ? "warning"
    : afterShift > threshold - 8
    ? "neutral"
    : "positive";
  const primary = `${current.toFixed(1)}h / ${threshold.toFixed(1)}h this week`;
  const headroom = threshold - afterShift;
  const secondary = c.would_trigger_ot
    ? "This shift would push them into overtime"
    : headroom > 0
    ? `${headroom.toFixed(1)}h of headroom after this shift`
    : "This shift fits — next one would trigger OT";
  const peakNote =
    c.peak_week_hours > current + 0.01
      ? `Peaks at ${c.peak_week_hours.toFixed(1)}h in another week this month`
      : null;
  return { current, threshold, cap, primary, secondary, monthTotal, peakNote, tone };
}

const TONE_BAR: Record<RationaleTone, string> = {
  positive: "bg-emerald-500",
  neutral: "bg-sky-500",
  warning: "bg-amber-500",
  danger: "bg-rose-500",
};

const TONE_TEXT: Record<RationaleTone, string> = {
  positive: "text-emerald-700",
  neutral: "text-sky-700",
  warning: "text-amber-700",
  danger: "text-rose-700",
};

function WorkloadChart({ view }: { view: WorkloadView }) {
  const fillPct = clamp01(view.current / view.cap) * 100;
  const tickPct = clamp01(view.threshold / view.cap) * 100;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <div className={cn("text-xs font-semibold tabular-nums", TONE_TEXT[view.tone])}>
          {view.primary}
        </div>
        <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
          Workload
        </div>
      </div>

      {/* Bar */}
      <div className="mt-1.5 relative h-2.5 overflow-hidden rounded-full bg-slate-100 ring-1 ring-slate-200/70">
        <div
          className={cn(
            "h-full origin-left motion-safe:animate-bar-grow",
            TONE_BAR[view.tone],
          )}
          style={{ width: `${fillPct}%` }}
        />
        {/* OT threshold tick */}
        <div
          className="absolute inset-y-[-2px] w-px bg-slate-700/70"
          style={{ left: `${tickPct}%` }}
          aria-label="OT threshold"
        />
      </div>

      {/* Axis labels */}
      <div className="mt-1 flex items-center justify-between text-[10px] tabular-nums text-slate-500">
        <span>0</span>
        <span className="text-slate-700 font-medium" style={{ marginLeft: `${tickPct - 50}%` }}>
          OT line
        </span>
        <span>{view.cap}{view.threshold === WEEKLY_OT_HOURS ? "h" : ""}</span>
      </div>

      <div className={cn("mt-1.5 text-[11px]", TONE_TEXT[view.tone])}>
        {view.secondary}
      </div>
      <div className="mt-0.5 text-[11px] text-slate-500">{view.monthTotal}</div>
      {view.peakNote && (
        <div className="mt-0.5 text-[11px] text-slate-500">{view.peakNote}</div>
      )}
    </div>
  );
}

function FitLine({ candidate }: { candidate: ScoredCandidate }) {
  const homeT = typologyLabel(candidate.home_unit_typology);
  const targetT = typologyLabel(candidate.target_unit_typology);
  const desc = candidate.clinical_fit_description.toLowerCase();

  // Plain-English phrases. The home_unit code is already in the row header
  // above, and typology jargon is dropped except when it's the actual point
  // (specialty mismatch).
  let label: string;
  let tone: RationaleTone;

  if (candidate.is_home_unit) {
    label = "Home unit";
    tone = "positive";
  } else if (desc.includes("cross-trained")) {
    label = "Cross-trained for this unit";
    tone = "positive";
  } else if (desc.includes("clinical risk")) {
    label = `Specialty mismatch — usually works ${homeT.toLowerCase()}`;
    tone = "danger";
  } else if (desc.includes("acceptable")) {
    label = "Cross-cover · acceptable";
    tone = "warning";
  } else if (homeT && targetT && homeT === targetT) {
    label = "Same unit type";
    tone = "positive";
  } else {
    label = "Floats in";
    tone = "neutral";
  }

  return (
    <div className="flex items-center gap-2">
      <span className={cn("size-2 shrink-0 rounded-full", TONE_BAR[tone])} />
      <span className="text-xs font-medium text-slate-800">{label}</span>
    </div>
  );
}

// Positive-support badges. Surface reasons the scheduler can scan in <3s
// without re-reading the chart or fit line. Each badge is a single
// fact that supports calling this person — never duplicated elsewhere.
function buildSupportBadges(c: ScoredCandidate): string[] {
  const out: string[] = [];

  // Familiarity with the target unit — a strong float signal. Skipped when
  // the candidate is home (FitLine already says "Home unit", so this would
  // duplicate). Only shown for floats who have actually worked here.
  if (!c.is_home_unit && c.target_unit_shifts > 0) {
    const n = c.target_unit_shifts;
    out.push(`Knows this unit · ${n} shift${n === 1 ? "" : "s"}`);
  }

  if (c.has_adjacent_shift) {
    out.push("Adjacent shift");
  }

  if (c.distance_miles < 5) {
    out.push(`Close · ${c.distance_miles.toFixed(1)} mi`);
  }
  if (c.tenure_years != null && c.tenure_years >= 5) {
    out.push(`${Math.floor(c.tenure_years)} yr veteran`);
  }
  if (
    c.days_since_last_shift != null &&
    c.days_since_last_shift <= 7
  ) {
    out.push("Worked recently");
  }
  return out;
}

function SupportBadges({ candidate }: { candidate: ScoredCandidate }) {
  const labels = buildSupportBadges(candidate);
  if (labels.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {labels.map((label, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-700"
        >
          <CheckCircle2 className="size-3 shrink-0 text-blue-600 fill-blue-600" />
          <span>{label}</span>
        </span>
      ))}
    </div>
  );
}

function RationalePanel({ candidate }: { candidate: ScoredCandidate }) {
  const r = candidate.rationale;

  // Backwards-compat: legacy stored responses with plain-string rationale.
  if (typeof r === "string") {
    return (
      <div className="border-t bg-muted/20 px-4 py-3">
        <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
          {r}
        </p>
      </div>
    );
  }

  const workload = computeWorkload(candidate);
  const risks = r?.risks ?? [];

  return (
    <div className="border-t bg-slate-50/60 px-4 py-3 space-y-3">
      {/* Workload chart */}
      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
        <WorkloadChart view={workload} />
      </div>

      {/* Fit line + positive-support badges */}
      <div className="space-y-1.5">
        <FitLine candidate={candidate} />
        <SupportBadges candidate={candidate} />
      </div>

      {/* Watch-outs — only render when there is something to flag */}
      {risks.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50/60 px-2.5 py-2">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
            <ShieldAlert className="size-3" />
            Watch-outs
          </div>
          <ul className="mt-1 space-y-0.5">
            {risks.map((risk, i) => (
              <li
                key={i}
                className="flex gap-2 text-xs text-amber-900 leading-relaxed"
              >
                <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-600" />
                <span>{risk}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
