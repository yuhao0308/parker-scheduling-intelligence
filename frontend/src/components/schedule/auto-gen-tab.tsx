"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ShiftRow } from "@/components/schedule/shift-row";
import { StatusOrb } from "@/components/schedule/status-orb";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  CalendarDays,
  CalendarRange,
  CheckCircle2,
  Search,
  Sparkles,
  type LucideIcon,
  X,
  XCircle,
} from "lucide-react";
import {
  useAllActiveStaff,
  useAutogenSubmit,
  useAutogenSubmitMonth,
  useCommitDecisions,
  useCommitMonthlyDecisions,
  useConfirmations,
  useDemoConfig,
  useMonthlyConfirmations,
  useMonthlySchedule,
  useRemoveEntry,
  useUnits,
} from "@/lib/queries";
import type {
  AutogenSubmitResult,
  CalendarLoadingScope,
  ConfirmationEntry,
  ConfirmationStatus,
  StaffOut,
} from "@/lib/types";

interface AutoGenTabProps {
  year: number;
  month: number;
  weekStart: string;
  onWeekStartChange: (value: string) => void;
  onLoadingScopeChange?: (scope: CalendarLoadingScope | null) => void;
}

type ScheduleScope = "week" | "month";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Priority order when an employee has multiple entries this week — whichever
// is "most actionable" drives their row's orb color.
const STATUS_PRIORITY: Record<ConfirmationStatus, number> = {
  DECLINED: 5,
  PENDING: 4,
  UNSENT: 3,
  ACCEPTED: 2,
  REPLACED: 1,
};

interface EmployeeMembership {
  status: ConfirmationStatus;
  entries: ConfirmationEntry[];
  pendingEntries: ConfirmationEntry[];
  oldestPending: ConfirmationEntry | null;
}

type RowError = { message: string; retry: () => void };

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function formatWeekLabel(weekStart: string): string {
  const d = new Date(`${weekStart}T00:00:00`);
  return `${MONTH_SHORT[d.getMonth()]} ${d.getDate()}`;
}

export function AutoGenTab({
  year,
  month,
  weekStart,
  onWeekStartChange,
  onLoadingScopeChange,
}: AutoGenTabProps) {
  const [scheduleScope, setScheduleScope] = useState<ScheduleScope>("week");
  const { data: staff = [] } = useAllActiveStaff();
  const { data: units = [] } = useUnits();
  const { data: confirmations } = useConfirmations(
    weekStart,
    scheduleScope === "week",
  );
  const { data: monthlyConfirmations } = useMonthlyConfirmations(
    year,
    month,
    scheduleScope === "month",
  );
  const { data: demoConfig } = useDemoConfig();
  const weekStartDate = useMemo(
    () => new Date(`${weekStart}T00:00:00`),
    [weekStart],
  );
  const { data: monthlyForDemand } = useMonthlySchedule(
    weekStartDate.getFullYear(),
    weekStartDate.getMonth() + 1,
  );
  const { data: selectedMonthlySchedule } = useMonthlySchedule(year, month);
  const activeConfirmations =
    scheduleScope === "week" ? confirmations : monthlyConfirmations;

  const autogenMutation = useAutogenSubmit();
  const monthlyAutogenMutation = useAutogenSubmitMonth();
  const commitMutation = useCommitDecisions(weekStart);
  const commitMonthlyMutation = useCommitMonthlyDecisions(year, month);
  const removeMutation = useRemoveEntry(weekStart);

  // Drive the calendar's loading overlay. Week-scoped mutations highlight just
  // the affected week row; month-scoped ones overlay the whole grid.
  const weekBuilding = autogenMutation.isPending || commitMutation.isPending;
  const monthBuilding =
    monthlyAutogenMutation.isPending || commitMonthlyMutation.isPending;
  useEffect(() => {
    if (!onLoadingScopeChange) return;
    if (monthBuilding) {
      onLoadingScopeChange({
        kind: "month",
        year,
        month,
        label: `${MONTH_NAMES[month - 1]} ${year}`,
      });
    } else if (weekBuilding) {
      onLoadingScopeChange({
        kind: "week",
        weekStart,
        label: `week of ${formatWeekLabel(weekStart)}`,
      });
    } else {
      onLoadingScopeChange(null);
    }
  }, [
    monthBuilding,
    weekBuilding,
    year,
    month,
    weekStart,
    onLoadingScopeChange,
  ]);
  useEffect(() => {
    return () => onLoadingScopeChange?.(null);
  }, [onLoadingScopeChange]);

  // Pool: supervisor's checkbox selection. Until they touch it, derive from
  // the active week in week mode, or default to all staff in month mode.
  const [manualPool, setManualPool] = useState<Set<string> | null>(null);
  const [rowErrors, setRowErrors] = useState<Map<string, RowError>>(new Map());
  const [searchQuery, setSearchQuery] = useState("");
  const inFlightEntries = useRef<Set<number>>(new Set());

  // Per-entry scheduler intent. true = keep this assignment, false = reopen it
  // back into the pool. Default true on first sight.
  const [intents, setIntents] = useState<Map<number, boolean>>(new Map());
  const seenIntentIdsRef = useRef<Set<number>>(new Set());
  const [isCommitting, setIsCommitting] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);

  const derivedPool = useMemo(() => {
    if (manualPool) return manualPool;
    if (scheduleScope === "month") {
      return new Set(staff.map((s) => s.employee_id));
    }
    const seeded = new Set<string>();
    for (const e of activeConfirmations?.entries ?? []) {
      if (e.confirmation_status !== "REPLACED") seeded.add(e.employee_id);
    }
    return seeded;
  }, [manualPool, scheduleScope, staff, activeConfirmations]);
  const pool = derivedPool;
  const setPool = (updater: (prev: Set<string>) => Set<string>) => {
    setManualPool((prev) => updater(prev ?? derivedPool));
  };

  // Map employee_id → membership snapshot for this week.
  const byEmployee = useMemo(() => {
    const m = new Map<string, EmployeeMembership>();
    for (const e of activeConfirmations?.entries ?? []) {
      const existing = m.get(e.employee_id);
      if (!existing) {
        m.set(e.employee_id, {
          status: e.confirmation_status,
          entries: [e],
          pendingEntries:
            e.confirmation_status === "PENDING" ? [e] : [],
          oldestPending: null,
        });
      } else {
        existing.entries.push(e);
        if (e.confirmation_status === "PENDING")
          existing.pendingEntries.push(e);
        if (
          STATUS_PRIORITY[e.confirmation_status] >
          STATUS_PRIORITY[existing.status]
        ) {
          existing.status = e.confirmation_status;
        }
      }
    }
    for (const membership of m.values()) {
      membership.pendingEntries.sort((a, b) => {
        const ta = a.confirmation_sent_at
          ? Date.parse(a.confirmation_sent_at)
          : Number.MAX_SAFE_INTEGER;
        const tb = b.confirmation_sent_at
          ? Date.parse(b.confirmation_sent_at)
          : Number.MAX_SAFE_INTEGER;
        return ta - tb;
      });
      membership.oldestPending = membership.pendingEntries[0] ?? null;
    }
    return m;
  }, [activeConfirmations]);

  // Seed intents: every newly-appearing PENDING entry starts as "Keep"
  // (checked). Once the scheduler toggles it, we preserve their choice.
  useEffect(() => {
    if (!activeConfirmations) return;
    const currentPendingIds = new Set<number>();
    let changed = false;
    const next = new Map(intents);
    for (const e of activeConfirmations.entries) {
      if (e.confirmation_status === "PENDING") {
        currentPendingIds.add(e.entry_id);
        if (!seenIntentIdsRef.current.has(e.entry_id)) {
          seenIntentIdsRef.current.add(e.entry_id);
          next.set(e.entry_id, true);
          changed = true;
        }
      }
    }
    for (const id of next.keys()) {
      if (!currentPendingIds.has(id)) {
        next.delete(id);
        changed = true;
      }
    }
    if (changed) setIntents(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConfirmations]);

  const confirmationLabel = demoConfig?.confirmation_timeout_label ?? "2 hours";

  function toggle(employeeId: string) {
    setPool((prev) => {
      const next = new Set(prev);
      if (next.has(employeeId)) next.delete(employeeId);
      else next.add(employeeId);
      return next;
    });
  }

  function handleSubmit() {
    if (scheduleScope === "month") {
      monthlyAutogenMutation.mutate({
        year,
        month,
        employee_pool: Array.from(pool),
      });
      return;
    }

    autogenMutation.mutate({
      week_start: weekStart,
      employee_pool: Array.from(pool),
      preserve_pending: true,
    });
  }

  function setIntent(entryId: number, keep: boolean) {
    setIntents((prev) => {
      const next = new Map(prev);
      next.set(entryId, keep);
      return next;
    });
  }

  async function handleCommit() {
    if (!activeConfirmations) return;
    const pending = activeConfirmations.entries.filter(
      (e) => e.confirmation_status === "PENDING",
    );
    if (pending.length === 0) return;

    setIsCommitting(true);
    setCommitError(null);

    try {
      const result =
        scheduleScope === "month"
          ? await commitMonthlyMutation.mutateAsync({
              year,
              month,
              employee_pool: Array.from(pool),
              decisions: pending.map((entry) => ({
                entry_id: entry.entry_id,
                keep: intents.get(entry.entry_id) !== false,
              })),
            })
          : await commitMutation.mutateAsync({
              week_start: weekStart,
              employee_pool: Array.from(pool),
              decisions: pending.map((entry) => ({
                entry_id: entry.entry_id,
                keep: intents.get(entry.entry_id) !== false,
              })),
            });

      if (result.declined_employee_ids.length > 0) {
        const reducedPool = new Set(pool);
        for (const id of result.declined_employee_ids) reducedPool.delete(id);
        setManualPool(reducedPool);
      }

      if (result.skipped_count > 0) {
        setCommitError(
          `${result.skipped_count} shifts changed before commit and were skipped. Refresh and review again if needed.`,
        );
      }
    } catch (error) {
      setCommitError(
        (error as Error)?.message ?? "Commit failed. Please retry.",
      );
    } finally {
      setIsCommitting(false);
    }
  }

  function clearRowError(employeeId: string) {
    setRowErrors((prev) => {
      if (!prev.has(employeeId)) return prev;
      const next = new Map(prev);
      next.delete(employeeId);
      return next;
    });
  }

  function setRowError(employeeId: string, error: RowError) {
    setRowErrors((prev) => {
      const next = new Map(prev);
      next.set(employeeId, error);
      return next;
    });
  }

  function handleRemoveFromPool(
    employeeId: string,
    entries: ConfirmationEntry[],
  ) {
    const targets = entries.filter(
      (e) =>
        e.confirmation_status === "DECLINED" ||
        e.confirmation_status === "PENDING" ||
        e.confirmation_status === "UNSENT",
    );
    clearRowError(employeeId);
    for (const e of targets) {
      if (inFlightEntries.current.has(e.entry_id)) continue;
      inFlightEntries.current.add(e.entry_id);
      removeMutation.mutate(e.entry_id, {
        onError: (err) => {
          setRowError(employeeId, {
            message: (err as Error)?.message ?? "Failed to remove.",
            retry: () => handleRemoveFromPool(employeeId, entries),
          });
        },
        onSettled: () => {
          inFlightEntries.current.delete(e.entry_id);
        },
      });
    }
    setPool((prev) => {
      const next = new Set(prev);
      next.delete(employeeId);
      return next;
    });
  }

  const summary = activeConfirmations?.summary;
  const submitPending =
    scheduleScope === "week"
      ? autogenMutation.isPending
      : monthlyAutogenMutation.isPending;
  const submitDisabled = submitPending || pool.size === 0;
  const pendingCount = summary?.pending ?? 0;
  const acceptedCount = scheduleScope === "week" ? (summary?.accepted ?? 0) : 0;
  const commitDisabled =
    isCommitting ||
    pendingCount === 0 ||
    commitMutation.isPending ||
    commitMonthlyMutation.isPending ||
    autogenMutation.isPending ||
    monthlyAutogenMutation.isPending;
  const mutating =
    commitMutation.isPending ||
    commitMonthlyMutation.isPending ||
    removeMutation.isPending ||
    isCommitting;

  const unitCount = units.length;
  const { peopleSlots, assignedSlots, openSlots } = useMemo(() => {
    if (scheduleScope === "month") {
      if (!selectedMonthlySchedule) {
        const shifts = unitCount * new Date(year, month, 0).getDate() * 3;
        return { peopleSlots: shifts * 2, assignedSlots: 0, openSlots: 0 };
      }
      let required = 0;
      let assigned = 0;
      for (const day of selectedMonthlySchedule.days) {
        for (const slot of day.slots) {
          required += slot.required_count;
          assigned += slot.assigned_employees.length;
        }
      }
      return {
        peopleSlots: required,
        assignedSlots: assigned,
        openSlots: Math.max(0, required - assigned),
      };
    }

    if (!monthlyForDemand) {
      const shifts = unitCount * 7 * 3;
      return {
        peopleSlots: shifts * 2,
        assignedSlots: acceptedCount,
        openSlots: 0,
      };
    }
    const startMs = weekStartDate.getTime();
    const endMs = startMs + 7 * 24 * 60 * 60 * 1000;
    let required = 0;
    for (const day of monthlyForDemand.days) {
      const ms = Date.parse(`${day.date}T00:00:00`);
      if (ms < startMs || ms >= endMs) continue;
      for (const slot of day.slots) {
        required += slot.required_count;
      }
    }
    return { peopleSlots: required, assignedSlots: acceptedCount, openSlots: 0 };
  }, [
    acceptedCount,
    monthlyForDemand,
    month,
    scheduleScope,
    selectedMonthlySchedule,
    unitCount,
    weekStartDate,
    year,
  ]);

  // Intent preview — count how many checked vs. unchecked will be committed.
  const intentPreview = useMemo(() => {
    let keep = 0;
    let remove = 0;
    for (const e of activeConfirmations?.entries ?? []) {
      if (e.confirmation_status !== "PENDING") continue;
      if (intents.get(e.entry_id) === false) remove += 1;
      else keep += 1;
    }
    return { keep, remove };
  }, [activeConfirmations, intents]);

  const fillPercent =
    peopleSlots > 0
      ? Math.min(100, Math.round((assignedSlots / peopleSlots) * 100))
      : 0;
  const hasPool = staff.length > 0;

  const trimmedQuery = searchQuery.trim().toLowerCase();
  const visibleStaff = useMemo(() => {
    if (!trimmedQuery) return staff;
    return staff.filter((s) => s.name.toLowerCase().includes(trimmedQuery));
  }, [staff, trimmedQuery]);

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="grid grid-cols-2 rounded-lg border bg-muted/30 p-1">
          <ScopeButton
            active={scheduleScope === "week"}
            icon={CalendarDays}
            label="Week"
            onClick={() => setScheduleScope("week")}
          />
          <ScopeButton
            active={scheduleScope === "month"}
            icon={CalendarRange}
            label="Month"
            onClick={() => setScheduleScope("month")}
          />
        </div>
        {scheduleScope === "month" && (
          <div className="rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[11px] leading-snug text-amber-900">
            Monthly generation rebuilds {MONTH_NAMES[month - 1]} {year} from
            the selected pool and sends those assignments into this same review
            queue.
          </div>
        )}
      </div>

      {/* Week picker */}
      {scheduleScope === "week" ? (
        <div className="flex items-center justify-between gap-2">
          <Label
            htmlFor="autogen-week-start"
            className="text-xs text-muted-foreground"
          >
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
      ) : (
        <div className="flex items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2">
          <span className="text-xs text-muted-foreground">Month</span>
          <span className="text-xs font-medium">
            {MONTH_NAMES[month - 1]} {year}
          </span>
        </div>
      )}

      {/* Stat tile grid — progress at a glance */}
      <StatGrid
        scope={scheduleScope}
        poolSize={pool.size}
        staffTotal={staff.length}
        fillPercent={fillPercent}
        assigned={assignedSlots}
        demand={peopleSlots}
        pending={scheduleScope === "month" ? openSlots : pendingCount}
        confirmed={scheduleScope === "week" ? acceptedCount : assignedSlots}
      />

      {/* Review banner — only when there are pending decisions */}
      {pendingCount > 0 && (
        <ReviewBanner
          pendingCount={pendingCount}
          keepCount={intentPreview.keep}
          removeCount={intentPreview.remove}
          onFinalize={handleCommit}
          disabled={commitDisabled}
          isCommitting={isCommitting}
          error={commitError}
        />
      )}

      {/* Unfilled warning — only after a submit that couldn't fill everything */}
      {scheduleScope === "week" &&
        autogenMutation.isSuccess &&
        autogenMutation.data &&
        autogenMutation.data.unfilled_slots > 0 && (
          <UnfilledCallout
            count={autogenMutation.data.unfilled_slots}
            warnings={autogenMutation.data.warnings}
          />
        )}

      {scheduleScope === "month" &&
        monthlyAutogenMutation.isSuccess &&
        monthlyAutogenMutation.data &&
        monthlyAutogenMutation.data.unfilled_slots > 0 && (
          <UnfilledCallout
            count={monthlyAutogenMutation.data.unfilled_slots}
            warnings={monthlyAutogenMutation.data.warnings}
          />
        )}

      {/* Send success toast (auto-fades concept — just a subtle confirmation) */}
      {scheduleScope === "week" &&
        autogenMutation.isSuccess &&
        autogenMutation.data &&
        autogenMutation.data.unfilled_slots === 0 &&
        autogenMutation.data.entries_generated > 0 && (
          <div
            className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-xs text-emerald-800"
            role="status"
          >
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            <span>
              <strong>{autogenMutation.data.entries_generated}</strong> shift
              {autogenMutation.data.entries_generated === 1 ? "" : "s"} assigned ·{" "}
              <strong>{autogenMutation.data.notifications_sent}</strong> invite
              {autogenMutation.data.notifications_sent === 1 ? "" : "s"} sent ·
              replies due within {confirmationLabel}
            </span>
          </div>
        )}

      {scheduleScope === "month" &&
        monthlyAutogenMutation.isSuccess &&
        monthlyAutogenMutation.data &&
        monthlyAutogenMutation.data.unfilled_slots === 0 && (
          <div
            className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-2 text-xs text-emerald-800"
            role="status"
          >
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
            <span>
              <strong>{monthlyAutogenMutation.data.entries_generated}</strong>{" "}
              shift
              {monthlyAutogenMutation.data.entries_generated === 1 ? "" : "s"}{" "}
              scheduled for {MONTH_NAMES[month - 1]} {year}
            </span>
          </div>
        )}

      {/* Pool toolbar */}
      {hasPool && (
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-xs">
              <span className="font-semibold">Staff pool</span>
              <span className="ml-1.5 text-muted-foreground">
                · {pool.size} of {staff.length}
                {trimmedQuery && (
                  <span className="ml-1">
                    · {visibleStaff.length} shown
                  </span>
                )}
              </span>
            </div>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() =>
                  setManualPool(new Set(staff.map((s) => s.employee_id)))
                }
                disabled={pool.size === staff.length}
                className="rounded-md border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Select all
              </button>
              <button
                type="button"
                onClick={() => setManualPool(new Set())}
                disabled={pool.size === 0}
                className="rounded-md border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Clear
              </button>
            </div>
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              role="searchbox"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name"
              aria-label="Search staff by name"
              className="h-8 pl-8 pr-8 text-xs [&::-webkit-search-cancel-button]:appearance-none [&::-webkit-search-decoration]:appearance-none"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                aria-label="Clear search"
                className="absolute right-1.5 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Scrollable pool list */}
      <div className="max-h-[55vh] overflow-y-auto rounded-lg border bg-card divide-y">
        {staff.length === 0 ? (
          <div className="p-4 text-xs text-muted-foreground">Loading staff…</div>
        ) : visibleStaff.length === 0 ? (
          <div className="p-4 text-xs text-muted-foreground">
            No staff match &ldquo;{searchQuery}&rdquo;.
          </div>
        ) : (
          visibleStaff.map((s) => {
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
                pendingCount={membership?.pendingEntries.length ?? 0}
                acceptedCount={
                  membership?.entries.filter(
                    (e) => e.confirmation_status === "ACCEPTED",
                  ).length ?? 0
                }
                declinedCount={
                  membership?.entries.filter(
                    (e) => e.confirmation_status === "DECLINED",
                  ).length ?? 0
                }
                confirmationLabel={confirmationLabel}
                intents={intents}
                onIntentChange={setIntent}
                onToggle={() => toggle(s.employee_id)}
                onRemoveFromPool={() =>
                  handleRemoveFromPool(
                    s.employee_id,
                    membership?.entries ?? [],
                  )
                }
                error={rowErrors.get(s.employee_id) ?? null}
                mutating={mutating}
              />
            );
          })
        )}
      </div>

      {/* Footer — Send invites CTA */}
      <div className="flex items-center justify-between gap-3 pt-1">
        <div className="text-[11px] text-muted-foreground leading-tight">
          {scheduleScope === "month" ? (
            "Builds the selected month from the checked staff pool"
          ) : pendingCount > 0 ? (
            <span className="text-amber-700">
              {pendingCount} pending{" "}
              {pendingCount === 1 ? "reply" : "replies"} won&apos;t be re-sent
            </span>
          ) : pool.size === 0 ? (
            "Add staff to pool to enable sending"
          ) : (
            "Sends invites to newly added pool members"
          )}
        </div>
        <Button
          size="sm"
          onClick={handleSubmit}
          disabled={submitDisabled}
          className="gap-1.5 h-8"
          aria-label={
            scheduleScope === "month"
              ? `Generate schedule for ${MONTH_NAMES[month - 1]} ${year}`
              : "Send invites to newly added pool members"
          }
        >
          <Sparkles className="h-3.5 w-3.5" />
          {submitPending
            ? "Building…"
            : scheduleScope === "month"
              ? "Build month"
              : "Build & send invites"}
        </Button>
      </div>

      {scheduleScope === "week" && autogenMutation.isError && (
        <div
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
          role="alert"
        >
          <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            {(autogenMutation.error as Error)?.message ?? "Send failed."}
          </span>
        </div>
      )}

      {scheduleScope === "month" && monthlyAutogenMutation.isError && (
        <div
          className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
          role="alert"
        >
          <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            {(monthlyAutogenMutation.error as Error)?.message ??
              "Monthly generation failed."}
          </span>
        </div>
      )}
    </div>
  );
}

function ScopeButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex h-8 items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  );
}

/* ── Stat grid ───────────────────────────────────────────────────────── */

interface StatGridProps {
  scope: ScheduleScope;
  poolSize: number;
  staffTotal: number;
  fillPercent: number;
  assigned: number;
  demand: number;
  pending: number;
  confirmed: number;
}

function StatGrid({
  scope,
  poolSize,
  staffTotal,
  fillPercent,
  assigned,
  demand,
  pending,
  confirmed,
}: StatGridProps) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {/* Filled — hero tile with progress bar */}
      <div className="col-span-2 rounded-lg border bg-card px-4 py-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {scope === "month" ? "Month progress" : "Week progress"}
          </span>
          <span className="text-[11px] text-muted-foreground tabular-nums">
            {assigned} / {demand} shifts
          </span>
        </div>
        <div className="mt-1 flex items-baseline gap-1.5">
          <span className="text-2xl font-bold tabular-nums tracking-tight">
            {fillPercent}%
          </span>
          <span className="text-xs text-muted-foreground">filled</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              fillPercent >= 100
                ? "bg-emerald-500"
                : fillPercent >= 80
                  ? "bg-sky-500"
                  : "bg-amber-500",
            )}
            style={{ width: `${Math.max(fillPercent, 2)}%` }}
          />
        </div>
      </div>

      <StatTile label="Pool" value={poolSize} sublabel={`of ${staffTotal}`} />
      <StatTile
        label={scope === "month" ? "Open" : "Waiting"}
        value={pending}
        sublabel={
          pending === 0
            ? "—"
            : scope === "month"
              ? "shifts"
              : "awaiting reply"
        }
        tone={pending > 0 ? "amber" : undefined}
      />
      <StatTile
        label={scope === "month" ? "Assigned" : "Confirmed"}
        value={confirmed}
        sublabel="shifts"
        tone={confirmed > 0 ? "emerald" : undefined}
      />
      <StatTile
        label="Demand"
        value={demand}
        sublabel="shifts"
      />
    </div>
  );
}

function StatTile({
  label,
  value,
  sublabel,
  tone,
}: {
  label: string;
  value: number;
  sublabel?: string;
  tone?: "amber" | "emerald" | "red";
}) {
  const toneClass =
    tone === "amber"
      ? "text-amber-700"
      : tone === "emerald"
        ? "text-emerald-700"
        : tone === "red"
          ? "text-red-700"
          : "";
  return (
    <div className="rounded-lg border bg-card px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={cn("text-xl font-bold tabular-nums leading-tight mt-0.5", toneClass)}>
        {value}
      </div>
      {sublabel && (
        <div className="text-[10px] text-muted-foreground leading-tight">
          {sublabel}
        </div>
      )}
    </div>
  );
}

/* ── Review banner ───────────────────────────────────────────────────── */

interface ReviewBannerProps {
  pendingCount: number;
  keepCount: number;
  removeCount: number;
  onFinalize: () => void;
  disabled: boolean;
  isCommitting: boolean;
  error: string | null;
}

function ReviewBanner({
  pendingCount,
  keepCount,
  removeCount,
  onFinalize,
  disabled,
  isCommitting,
  error,
}: ReviewBannerProps) {
  return (
    <div className="rounded-lg border border-sky-300 bg-sky-50/80 p-3 space-y-2.5">
      <div className="flex items-start gap-2.5">
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-200/70 mt-0.5">
          <span className="text-[11px] font-bold text-sky-900 tabular-nums">
            {pendingCount}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-sky-900">
            {pendingCount === 1 ? "Invite" : "Invites"} ready to review
          </div>
          <p className="text-[11px] text-sky-900/70 leading-snug">
            Keep confirmed replies. Reopen declines to put the shift back into
            the pool.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 pl-8">
        <div className="flex items-center gap-3 text-xs text-sky-900/90 tabular-nums">
          <span className="inline-flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3" />
            <strong>{keepCount}</strong> keep
          </span>
          <span className="text-sky-900/40">·</span>
          <span className="inline-flex items-center gap-1">
            <XCircle className="h-3 w-3" />
            <strong>{removeCount}</strong> reopen
          </span>
        </div>
        <Button
          size="sm"
          onClick={onFinalize}
          disabled={disabled}
          className="h-7 px-3 text-xs gap-1"
          aria-label={`Commit ${pendingCount} decisions`}
        >
          {isCommitting ? "Locking in…" : `Lock in ${pendingCount}`}
        </Button>
      </div>

      {error && (
        <div
          className="rounded border border-destructive/30 bg-white px-2 py-1.5 text-[11px] text-destructive ml-8"
          role="alert"
        >
          {error}
        </div>
      )}
    </div>
  );
}

/* ── Unfilled callout ────────────────────────────────────────────────── */

interface UnfilledCalloutProps {
  count: number;
  warnings: string[];
}

function UnfilledCallout({ count, warnings }: UnfilledCalloutProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50/80 p-3 space-y-2">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-700 mt-0.5" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-amber-900">
            {count} slot{count === 1 ? "" : "s"} couldn&apos;t be filled
          </div>
          <p className="text-[11px] text-amber-900/70 leading-snug">
            Add more people to the pool or broaden license coverage, then
            generate again.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-[11px] text-amber-900/80 underline hover:text-amber-900 shrink-0"
        >
          {open ? "Hide" : "Details"}
        </button>
      </div>
      {open && warnings.length > 0 && (
        <ul className="mt-1 pl-6 list-disc space-y-0.5 text-[11px] text-amber-900/80 max-h-32 overflow-y-auto">
          {warnings.map((w, i) => (
            <li key={i} className="tabular-nums">
              {w}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── Row (unchanged logic) ───────────────────────────────────────────── */

interface StaffRowProps {
  staff: StaffOut;
  checked: boolean;
  status: ConfirmationStatus | null;
  entries: ConfirmationEntry[];
  pendingCount: number;
  acceptedCount: number;
  declinedCount: number;
  confirmationLabel: string;
  intents: Map<number, boolean>;
  onIntentChange: (entryId: number, keep: boolean) => void;
  onToggle: () => void;
  onRemoveFromPool: () => void;
  error: RowError | null;
  mutating: boolean;
}

function sortEntries(entries: ConfirmationEntry[]): ConfirmationEntry[] {
  const shiftRank: Record<string, number> = { DAY: 0, EVENING: 1, NIGHT: 2 };
  return entries.slice().sort((a, b) => {
    if (a.shift_date !== b.shift_date)
      return a.shift_date.localeCompare(b.shift_date);
    return (shiftRank[a.shift_label] ?? 9) - (shiftRank[b.shift_label] ?? 9);
  });
}

function StaffRow({
  staff,
  checked,
  status,
  entries,
  pendingCount,
  acceptedCount,
  declinedCount,
  confirmationLabel,
  intents,
  onIntentChange,
  onToggle,
  onRemoveFromPool,
  error,
  mutating,
}: StaffRowProps) {
  const isDeclined = status === "DECLINED";
  const uncheckedWithPending = !checked && pendingCount > 0;
  const hasEntries = entries.length > 0;

  const sortedEntries = hasEntries ? sortEntries(entries) : [];

  const summaryBits: string[] = [];
  if (acceptedCount > 0) summaryBits.push(`${acceptedCount} accepted`);
  if (pendingCount > 0) summaryBits.push(`${pendingCount} pending`);
  if (declinedCount > 0) summaryBits.push(`${declinedCount} declined`);
  const statusSummary = summaryBits.join(" · ");

  const shouldAutoExpand = pendingCount > 0;

  return (
    <div className="px-3 py-2 text-sm">
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          className="h-4 w-4 shrink-0 mt-1 accent-primary"
          checked={checked}
          onChange={onToggle}
          aria-label={`Include ${staff.name} in pool`}
        />
        <details className="min-w-0 flex-1 group" open={shouldAutoExpand}>
          <summary className="flex items-start gap-2 cursor-pointer list-none outline-none focus-visible:underline">
            <div className="mt-1 shrink-0">
              <StatusOrb status={status} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-medium truncate">
                {staff.name}{" "}
                <span className="text-xs text-muted-foreground font-normal">
                  ({staff.license})
                </span>
              </div>
              <div className="text-[11px] text-muted-foreground truncate">
                {staff.home_unit_id ?? "—"}
                {hasEntries && (
                  <span className="ml-1">
                    · {entries.length} shift
                    {entries.length === 1 ? "" : "s"}
                  </span>
                )}
                {statusSummary && (
                  <span className="ml-1">· {statusSummary}</span>
                )}
              </div>
              {uncheckedWithPending && (
                <div
                  className="text-[11px] text-amber-700 mt-0.5"
                  role="note"
                >
                  Removed from pool — {pendingCount} pending invite
                  {pendingCount === 1 ? "" : "s"} still open. Use &ldquo;Remove
                  from pool&rdquo; to cancel them.
                </div>
              )}
              {error && (
                <div
                  className="text-[11px] text-destructive mt-0.5 flex items-center gap-2"
                  role="alert"
                >
                  <span>{error.message}</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      error.retry();
                    }}
                    className="underline hover:no-underline"
                    aria-label={`Retry last action for ${staff.name}`}
                  >
                    Retry
                  </button>
                </div>
              )}
            </div>
            {hasEntries && (
              <span
                aria-hidden
                className="shrink-0 text-[10px] text-muted-foreground transition-transform group-open:rotate-90"
                title="Show per-shift detail"
              >
                ▸
              </span>
            )}
          </summary>
          {hasEntries && (
            <div className="mt-1 space-y-0.5">
              {sortedEntries.map((entry) => (
                <ShiftRow
                  key={entry.entry_id}
                  entry={entry}
                  employeeName={staff.name}
                  confirmationLabel={confirmationLabel}
                  intent={intents.get(entry.entry_id) !== false}
                  onIntentChange={(next) =>
                    onIntentChange(entry.entry_id, next)
                  }
                  disabled={mutating}
                />
              ))}
            </div>
          )}
        </details>

        {isDeclined && (
          <Button
            size="sm"
            variant="outline"
            className="h-6 px-1.5 text-[11px] text-red-700 border-red-200 hover:bg-red-50 shrink-0"
            onClick={onRemoveFromPool}
            disabled={mutating}
            aria-label={`Remove ${staff.name} from pool`}
          >
            Remove from list
          </Button>
        )}
      </div>
    </div>
  );
}

// Unused but kept as part of the public-ish API surface of this module.
export type { AutogenSubmitResult };
