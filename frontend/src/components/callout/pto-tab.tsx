"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, XCircle, AlertCircle, Calendar, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  useAllActiveStaff,
  useMonthlySchedule,
  useSubmitCallout,
} from "@/lib/queries";
import {
  seedDemoPtoRequestsIfNeeded,
  setPtoStatus,
  updatePtoRequest,
  useDemoPtoRequests,
  type PtoRequest,
} from "@/lib/pto-mock";
import type {
  MonthlySchedule,
  ShiftLabel,
  ShiftSlot,
} from "@/lib/types";

const LICENSE_BADGE: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800 border-blue-200",
  LPN: "bg-green-100 text-green-800 border-green-200",
  CNA: "bg-amber-100 text-amber-800 border-amber-200",
  PCT: "bg-purple-100 text-purple-800 border-purple-200",
};

// Fallback shift duration when no value is available on ShiftSlot.
// Production should derive this from the actual shift definition.
const DEFAULT_SHIFT_HOURS = 8;

const STATUS_STYLE: Record<
  PtoRequest["status"],
  { label: string; className: string; icon: React.ElementType }
> = {
  PENDING: {
    label: "Pending",
    className: "bg-amber-100 text-amber-800 border-amber-200",
    icon: AlertCircle,
  },
  APPROVED: {
    label: "Approved",
    className: "bg-emerald-100 text-emerald-800 border-emerald-200",
    icon: CheckCircle2,
  },
  REJECTED: {
    label: "Rejected",
    className: "bg-red-100 text-red-800 border-red-200",
    icon: XCircle,
  },
};

export function PtoTab() {
  const router = useRouter();
  const requests = useDemoPtoRequests();
  const { data: staff = [] } = useAllActiveStaff();

  // Seed once on first load — uses real staff IDs so generated callouts work.
  useEffect(() => {
    if (staff.length > 0) seedDemoPtoRequestsIfNeeded(staff);
  }, [staff]);

  // Pre-fetch the monthly schedule for the current month + the next two so
  // we can find affected shifts inside the typical PTO request range.
  const today = useMemo(() => new Date(), []);
  const m1 = { y: today.getFullYear(), m: today.getMonth() + 1 };
  const m2nd = nextMonth(m1.y, m1.m);
  const m3rd = nextMonth(m2nd.y, m2nd.m);
  const sched1 = useMonthlySchedule(m1.y, m1.m).data;
  const sched2 = useMonthlySchedule(m2nd.y, m2nd.m).data;
  const sched3 = useMonthlySchedule(m3rd.y, m3rd.m).data;
  const allSchedules = useMemo(
    () => [sched1, sched2, sched3].filter(Boolean) as MonthlySchedule[],
    [sched1, sched2, sched3],
  );

  const submitCallout = useSubmitCallout();
  const [busyId, setBusyId] = useState<string | null>(null);

  async function handleApprove(req: PtoRequest) {
    setBusyId(req.id);
    try {
      const affected = findFirstAffectedShift(req, allSchedules);

      // TODO production: process all affected shifts in [start_date, end_date].
      // For demo we only convert the first match into a vacancy.
      let sickBalance = req.sick_balance;
      let ptoBalance = req.pto_balance;
      let sickUsed = 0;
      let ptoUsed = 0;
      let calloutId: number | undefined;
      let affectedRecord: PtoRequest["affected_shift"] | undefined;

      if (affected) {
        const hours = affected.hours;
        sickUsed = Math.min(sickBalance, hours);
        sickBalance -= sickUsed;
        const remaining = hours - sickUsed;
        ptoUsed = Math.min(ptoBalance, remaining);
        ptoBalance -= ptoUsed;

        affectedRecord = {
          shift_date: affected.slot.shift_date,
          shift_label: affected.slot.shift_label,
          unit_id: affected.slot.unit_id,
          hours_used: hours,
          sick_used: sickUsed,
          pto_used: ptoUsed,
        };

        // Reuse the existing call-out replacement engine: convert this shift
        // into a vacancy by submitting a callout for the requesting employee.
        try {
          const job = await submitCallout.mutateAsync({
            callout_employee_id: req.employee_id,
            unit_id: affected.slot.unit_id,
            shift_date: affected.slot.shift_date,
            shift_label: affected.slot.shift_label,
          });
          calloutId = job.callout_id;
        } catch (err) {
          console.error("PTO → callout submission failed", err);
        }
      }

      updatePtoRequest(req.id, {
        status: "APPROVED",
        decided_at: new Date().toISOString(),
        sick_balance: sickBalance,
        pto_balance: ptoBalance,
        affected_shift: affectedRecord,
        callout_id: calloutId,
      });

      if (calloutId) {
        // Auto-navigate the scheduler into the existing call-out flow so they
        // can review recommendations for the now-vacant shift.
        router.push(`/callout?callout_id=${calloutId}&tab=callout`);
      }
    } finally {
      setBusyId(null);
    }
  }

  function handleReject(req: PtoRequest) {
    setPtoStatus(req.id, "REJECTED");
  }

  const pending = requests.filter((r) => r.status === "PENDING");
  const decided = requests.filter((r) => r.status !== "PENDING");

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-dashed border-amber-300 bg-amber-50 px-4 py-2.5 text-xs text-amber-900">
        <strong className="font-semibold">Demo HR integration:</strong> these
        leave requests are generated locally to emulate an HR system feed. In
        production, requests would arrive via real PTO accrual / SmartLinx
        sync.
      </div>

      <Section title="Pending requests" count={pending.length}>
        {pending.length === 0 ? (
          <EmptyRow text="No pending requests." />
        ) : (
          pending.map((r) => (
            <RequestCard
              key={r.id}
              request={r}
              isBusy={busyId === r.id}
              onApprove={() => handleApprove(r)}
              onReject={() => handleReject(r)}
            />
          ))
        )}
      </Section>

      <Section title="Decided" count={decided.length}>
        {decided.length === 0 ? (
          <EmptyRow text="Nothing decided yet." />
        ) : (
          decided.map((r) => (
            <RequestCard key={r.id} request={r} isBusy={false} />
          ))
        )}
      </Section>
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </h3>
        <span className="text-xs text-muted-foreground">{count}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <div className="rounded-md border bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
      {text}
    </div>
  );
}

function RequestCard({
  request,
  isBusy,
  onApprove,
  onReject,
}: {
  request: PtoRequest;
  isBusy: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const status = STATUS_STYLE[request.status];
  const StatusIcon = status.icon;
  const dateRange =
    request.start_date === request.end_date
      ? formatDate(request.start_date)
      : `${formatDate(request.start_date)} – ${formatDate(request.end_date)}`;

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-base font-semibold">
                {request.employee_name}
              </span>
              <Badge
                variant="secondary"
                className={cn(
                  "border text-[11px] px-1.5 py-0",
                  LICENSE_BADGE[request.license] ?? "",
                )}
              >
                {request.license}
              </Badge>
              {request.home_unit_id && (
                <span className="text-xs text-muted-foreground">
                  · {request.home_unit_id}
                </span>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Calendar className="h-3 w-3" /> {dateRange}
              </span>
              <span>·</span>
              <span>{request.request_type}</span>
              <span>·</span>
              <span>{request.total_hours}h requested</span>
            </div>
          </div>
          <Badge variant="secondary" className={cn("border", status.className)}>
            <StatusIcon className="mr-1 inline h-3 w-3" />
            {status.label}
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-md bg-muted/40 px-3 py-2">
            <div className="text-muted-foreground uppercase tracking-wide text-[10px]">
              Sick balance
            </div>
            <div className="font-semibold">{request.sick_balance}h</div>
          </div>
          <div className="rounded-md bg-muted/40 px-3 py-2">
            <div className="text-muted-foreground uppercase tracking-wide text-[10px]">
              PTO balance
            </div>
            <div className="font-semibold">{request.pto_balance}h</div>
          </div>
        </div>

        {request.affected_shift && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
            Marked {request.affected_shift.shift_label} on{" "}
            {formatDate(request.affected_shift.shift_date)} ({request.affected_shift.unit_id})
            as leave. Sick used: {request.affected_shift.sick_used}h · PTO used:{" "}
            {request.affected_shift.pto_used}h.
            {request.callout_id && (
              <>
                {" "}
                <a
                  className="underline font-medium"
                  href={`/callout?callout_id=${request.callout_id}`}
                >
                  Open replacement flow →
                </a>
              </>
            )}
          </div>
        )}

        {request.status === "PENDING" && onApprove && onReject && (
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onReject}
              disabled={isBusy}
            >
              <XCircle className="mr-1 h-3.5 w-3.5" />
              Reject
            </Button>
            <Button size="sm" onClick={onApprove} disabled={isBusy}>
              {isBusy ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
              )}
              Approve & Find Replacement
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface AffectedShift {
  slot: ShiftSlot;
  hours: number;
}

function findFirstAffectedShift(
  req: PtoRequest,
  schedules: MonthlySchedule[],
): AffectedShift | null {
  const start = req.start_date;
  const end = req.end_date;
  for (const sched of schedules) {
    for (const day of sched.days) {
      if (day.date < start || day.date > end) continue;
      for (const slot of day.slots) {
        const isAssigned = slot.assigned_employees.some(
          (e) => e.employee_id === req.employee_id,
        );
        if (isAssigned) {
          return { slot, hours: shiftHours(slot.shift_label) };
        }
      }
    }
  }
  return null;
}

function shiftHours(_label: ShiftLabel): number {
  // Demo assumption — Parker uses standard 8-hour shifts.
  return DEFAULT_SHIFT_HOURS;
}

function nextMonth(y: number, m: number): { y: number; m: number } {
  if (m === 12) return { y: y + 1, m: 1 };
  return { y, m: m + 1 };
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map((n) => parseInt(n, 10));
  if (!y || !m || !d) return iso;
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
