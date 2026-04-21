"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusOrb } from "@/components/schedule/status-orb";
import { useCountdown } from "@/components/schedule/use-countdown";
import {
  useAllActiveStaff,
  useAutogenSubmit,
  useConfirmations,
  useDemoConfig,
  useRemoveEntry,
  useRespondConfirmation,
} from "@/lib/queries";
import type {
  CalloutResponse,
  ConfirmationEntry,
  ConfirmationStatus,
  StaffOut,
} from "@/lib/types";

interface AutoGenTabProps {
  weekStart: string;
  onWeekStartChange: (value: string) => void;
  onDeclineReplacement: (
    entry: ConfirmationEntry,
    replacement: CalloutResponse,
  ) => void;
}

// Priority order when an employee has multiple entries this week — whichever
// is "most actionable" drives their row's orb color.
const STATUS_PRIORITY: Record<ConfirmationStatus, number> = {
  DECLINED: 5,
  PENDING: 4,
  UNSENT: 3,
  ACCEPTED: 2,
  REPLACED: 1,
};

/**
 * Auto-Gen tab: pool picker + submit + inline reply console.
 *
 * The supervisor mockup asks for a single pane that:
 *   1. lists every active employee with a checkbox (pool membership)
 *   2. shows a colored orb per employee reflecting weekly confirmation state
 *   3. offers a Submit button that generates + sends confirmations atomically
 *   4. lets the scheduler simulate Accept/Decline/Timeout inline
 *   5. for DECLINED rows, exposes a one-click "Remove from pool" (absorbs
 *      the entry into REPLACED with no replacement, freeing the slot for a
 *      future re-submit with a different pool).
 */
export function AutoGenTab({
  weekStart,
  onWeekStartChange,
  onDeclineReplacement,
}: AutoGenTabProps) {
  const { data: staff = [] } = useAllActiveStaff();
  const { data: confirmations } = useConfirmations(weekStart);
  const { data: demoConfig } = useDemoConfig();

  const autogenMutation = useAutogenSubmit();
  const respondMutation = useRespondConfirmation(weekStart);
  const removeMutation = useRemoveEntry(weekStart);

  // Track if scheduler has manually touched the pool; until then derive it
  // from whoever's already on the week (so returning to the tab mid-flow
  // shows the right checkboxes without a sync effect).
  const [manualPool, setManualPool] = useState<Set<string> | null>(null);
  const [timedOut, setTimedOut] = useState<Set<number>>(new Set());

  const derivedPool = useMemo(() => {
    if (manualPool) return manualPool;
    const seeded = new Set<string>();
    for (const e of confirmations?.entries ?? []) {
      if (e.confirmation_status !== "REPLACED") seeded.add(e.employee_id);
    }
    return seeded;
  }, [manualPool, confirmations]);
  const pool = derivedPool;
  const setPool = (updater: (prev: Set<string>) => Set<string>) => {
    setManualPool((prev) => updater(prev ?? derivedPool));
  };

  // Map employee_id → {status, entry} for this week.
  const byEmployee = useMemo(() => {
    const m = new Map<
      string,
      { status: ConfirmationStatus; entries: ConfirmationEntry[] }
    >();
    for (const e of confirmations?.entries ?? []) {
      const existing = m.get(e.employee_id);
      if (!existing) {
        m.set(e.employee_id, {
          status: e.confirmation_status,
          entries: [e],
        });
      } else {
        existing.entries.push(e);
        if (
          STATUS_PRIORITY[e.confirmation_status] >
          STATUS_PRIORITY[existing.status]
        ) {
          existing.status = e.confirmation_status;
        }
      }
    }
    return m;
  }, [confirmations]);

  function toggle(employeeId: string) {
    setPool((prev) => {
      const next = new Set(prev);
      if (next.has(employeeId)) next.delete(employeeId);
      else next.add(employeeId);
      return next;
    });
  }

  function handleSubmit() {
    autogenMutation.mutate({
      week_start: weekStart,
      employee_pool: Array.from(pool),
      preserve_pending: true,
    });
  }

  function handleRespond(
    entry: ConfirmationEntry,
    response: "ACCEPTED" | "DECLINED" | "TIMEOUT",
  ) {
    respondMutation.mutate(
      { entryId: entry.entry_id, req: { response } },
      {
        onSuccess: (result) => {
          if (result.replacement) {
            onDeclineReplacement(entry, result.replacement);
          }
        },
      },
    );
  }

  function handleRemoveFromPool(employeeId: string, entries: ConfirmationEntry[]) {
    // Remove every DECLINED/PENDING/UNSENT entry for this employee this week.
    // ACCEPTED rows are left alone (locked shifts).
    const targets = entries.filter(
      (e) =>
        e.confirmation_status === "DECLINED" ||
        e.confirmation_status === "PENDING" ||
        e.confirmation_status === "UNSENT",
    );
    if (targets.length === 0) return;
    for (const e of targets) {
      removeMutation.mutate(e.entry_id);
    }
    setPool((prev) => {
      const next = new Set(prev);
      next.delete(employeeId);
      return next;
    });
  }

  const summary = confirmations?.summary;
  const hasPending = (summary?.pending ?? 0) > 0;
  const submitDisabled =
    autogenMutation.isPending || pool.size === 0 || hasPending;

  const confirmationLabel = demoConfig?.confirmation_timeout_label ?? "2 hours";
  const confirmationSeconds = demoConfig?.confirmation_timeout_seconds ?? 15;

  return (
    <div className="space-y-3">
      {/* Week picker */}
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor="autogen-week-start" className="text-xs text-muted-foreground">
          Week of
        </Label>
        <Input
          id="autogen-week-start"
          type="date"
          value={weekStart}
          onChange={(e) => onWeekStartChange(e.target.value)}
          className="h-8 text-xs w-40"
        />
      </div>

      {/* Summary badges */}
      {summary && (
        <div className="flex gap-1.5 flex-wrap text-[11px]">
          <Badge className="bg-amber-100 text-amber-800">
            {summary.pending} pending
          </Badge>
          <Badge className="bg-emerald-100 text-emerald-800">
            {summary.accepted} accepted
          </Badge>
          <Badge className="bg-red-100 text-red-800">
            {summary.declined} declined
          </Badge>
          <Badge className="bg-slate-100 text-slate-600">
            {summary.replaced} replaced
          </Badge>
        </div>
      )}

      {/* Scrollable pool list */}
      <div className="max-h-[55vh] overflow-y-auto border rounded-md divide-y">
        {staff.length === 0 ? (
          <div className="p-4 text-xs text-muted-foreground">Loading staff…</div>
        ) : (
          staff.map((s) => {
            const membership = byEmployee.get(s.employee_id);
            const status: ConfirmationStatus | null = membership?.status ?? null;
            const checked = pool.has(s.employee_id);
            return (
              <StaffRow
                key={s.employee_id}
                staff={s}
                checked={checked}
                status={status}
                entries={membership?.entries ?? []}
                onToggle={() => toggle(s.employee_id)}
                onRespond={handleRespond}
                onRemoveFromPool={() =>
                  handleRemoveFromPool(
                    s.employee_id,
                    membership?.entries ?? [],
                  )
                }
                confirmationLabel={confirmationLabel}
                confirmationSeconds={confirmationSeconds}
                timedOut={timedOut}
                markTimedOut={(id) =>
                  setTimedOut((set) => new Set(set).add(id))
                }
                mutating={
                  respondMutation.isPending || removeMutation.isPending
                }
              />
            );
          })
        )}
      </div>

      {/* Submit */}
      <div className="flex items-center justify-between gap-2 border-t pt-3">
        <div className="text-xs text-muted-foreground">
          {pool.size} employee{pool.size === 1 ? "" : "s"} in pool
          {hasPending && (
            <span className="ml-1 text-amber-700">
              · {summary?.pending} pending reply
              {summary?.pending === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={submitDisabled}
        >
          {autogenMutation.isPending ? "Submitting…" : "Submit"}
        </Button>
      </div>

      {autogenMutation.isSuccess && autogenMutation.data && (
        <div className="text-xs text-muted-foreground">
          {autogenMutation.data.entries_generated} new shift
          {autogenMutation.data.entries_generated === 1 ? "" : "s"} ·{" "}
          {autogenMutation.data.notifications_sent} confirmation
          {autogenMutation.data.notifications_sent === 1 ? "" : "s"} sent ·
          auto-accepts in {confirmationLabel}
        </div>
      )}

      {autogenMutation.isError && (
        <div className="text-xs text-destructive">
          {(autogenMutation.error as Error)?.message ?? "Submit failed."}
        </div>
      )}

      {respondMutation.isError && (
        <div className="text-xs text-destructive">
          {(respondMutation.error as Error)?.message ?? "Response failed."}
        </div>
      )}
    </div>
  );
}

// --- Row --------------------------------------------------------------

interface StaffRowProps {
  staff: StaffOut;
  checked: boolean;
  status: ConfirmationStatus | null;
  entries: ConfirmationEntry[];
  onToggle: () => void;
  onRespond: (
    entry: ConfirmationEntry,
    response: "ACCEPTED" | "DECLINED" | "TIMEOUT",
  ) => void;
  onRemoveFromPool: () => void;
  confirmationLabel: string;
  confirmationSeconds: number;
  timedOut: Set<number>;
  markTimedOut: (entryId: number) => void;
  mutating: boolean;
}

function StaffRow({
  staff,
  checked,
  status,
  entries,
  onToggle,
  onRespond,
  onRemoveFromPool,
  confirmationLabel,
  confirmationSeconds,
  timedOut,
  markTimedOut,
  mutating,
}: StaffRowProps) {
  const pendingEntry = entries.find(
    (e) =>
      e.confirmation_status === "PENDING" && !timedOut.has(e.entry_id),
  );
  const isDeclined = status === "DECLINED";

  const remaining = useCountdown(
    confirmationSeconds,
    !!pendingEntry,
    () => {
      if (pendingEntry) {
        markTimedOut(pendingEntry.entry_id);
        onRespond(pendingEntry, "TIMEOUT");
      }
    },
  );

  return (
    <div className="px-3 py-2 text-sm flex items-center gap-2">
      <input
        type="checkbox"
        className="h-4 w-4 shrink-0"
        checked={checked}
        onChange={onToggle}
        aria-label={`Include ${staff.name} in pool`}
      />
      <StatusOrb status={status} />
      <div className="min-w-0 flex-1">
        <div className="font-medium truncate">
          {staff.name}{" "}
          <span className="text-xs text-muted-foreground font-normal">
            ({staff.license})
          </span>
        </div>
        <div className="text-[11px] text-muted-foreground truncate">
          {staff.home_unit_id ?? "—"}
          {entries.length > 0 && (
            <span className="ml-1">
              · {entries.length} shift{entries.length === 1 ? "" : "s"} this
              week
            </span>
          )}
        </div>
      </div>

      {pendingEntry ? (
        <div className="flex items-center gap-1 shrink-0">
          <span
            className="text-[10px] text-muted-foreground tabular-nums"
            title={`Auto-accepts in ${confirmationLabel} (demo: ${remaining}s)`}
          >
            {remaining}s
          </span>
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-1.5 text-[11px]"
            onClick={() => onRespond(pendingEntry, "ACCEPTED")}
            disabled={mutating}
          >
            Accept
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-1.5 text-[11px] text-red-700 border-red-200 hover:bg-red-50"
            onClick={() => onRespond(pendingEntry, "DECLINED")}
            disabled={mutating}
          >
            Decline
          </Button>
        </div>
      ) : isDeclined ? (
        <Button
          size="sm"
          variant="outline"
          className="h-6 px-1.5 text-[11px] text-red-700 border-red-200 hover:bg-red-50 shrink-0"
          onClick={onRemoveFromPool}
          disabled={mutating}
        >
          Remove from pool
        </Button>
      ) : null}
    </div>
  );
}
