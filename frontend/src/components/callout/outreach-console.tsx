"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  useOutreach,
  useRespondOutreach,
  useSendOutreach,
} from "@/lib/queries";
import { CheckCircle2, XCircle, Clock, SkipForward, Send, Users } from "lucide-react";
import type { CalloutResponse, ScoredCandidate } from "@/lib/types";

const FILLED_BY_OTHER_MARKER = "filled by another teammate";

const STATUS_STYLE: Record<
  string,
  { label: string; className: string; icon?: React.ElementType }
> = {
  SENT: { label: "Awaiting reply", className: "bg-amber-100 text-amber-800 border-amber-200" },
  ACCEPTED: { label: "Accepted", className: "bg-emerald-100 text-emerald-800 border-emerald-200", icon: CheckCircle2 },
  DECLINED: { label: "Declined", className: "bg-red-100 text-red-800 border-red-200", icon: XCircle },
  TIMEOUT: { label: "Timed out", className: "bg-slate-100 text-slate-600 border-slate-200", icon: Clock },
  SKIPPED: { label: "Skipped", className: "bg-slate-100 text-slate-600 border-slate-200", icon: SkipForward },
  CANCELED: { label: "Canceled", className: "bg-slate-100 text-slate-400 border-slate-200 line-through" },
};

const FILLED_STYLE = {
  label: "Filled!",
  className: "bg-teal-100 text-teal-800 border-teal-200",
  icon: CheckCircle2,
};

interface OutreachConsoleProps {
  result: CalloutResponse;
  onAccepted: (assignedEntryId: number) => void;
}

export function OutreachConsole({ result, onAccepted }: OutreachConsoleProps) {
  const { data: notifications = [] } = useOutreach(result.callout_id);
  const sendMutation = useSendOutreach();
  const respondMutation = useRespondOutreach();

  const [deprioritized, setDeprioritized] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);

  const candidatesByEmp = useMemo(() => {
    const m = new Map<string, ScoredCandidate>();
    for (const c of result.candidates) m.set(c.employee_id, c);
    return m;
  }, [result.candidates]);

  const contacted = new Set(notifications.map((n) => n.employee_id));
  const pendings = notifications.filter((n) => n.status === "SENT");

  const orderedCandidates = useMemo(() => {
    const remaining: ScoredCandidate[] = [];
    const bottom: ScoredCandidate[] = [];
    for (const c of result.candidates) {
      if (deprioritized.has(c.employee_id)) bottom.push(c);
      else remaining.push(c);
    }
    return [...remaining, ...bottom];
  }, [result.candidates, deprioritized]);

  const uncontactedCandidates = orderedCandidates.filter(
    (c) => !contacted.has(c.employee_id),
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelected((prev) => {
      const next = new Set<string>();
      for (const id of prev) {
        if (!contacted.has(id)) next.add(id);
      }
      return next.size === prev.size ? prev : next;
    });
  }, [notifications]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleSelect(employeeId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(employeeId)) next.delete(employeeId);
      else next.add(employeeId);
      return next;
    });
  }

  function handleSendBatch(employeeIds: string[]) {
    for (const empId of employeeIds) {
      const c = candidatesByEmp.get(empId);
      if (!c) continue;
      sendMutation.mutate({
        calloutId: result.callout_id,
        req: {
          recommendation_log_id: result.recommendation_log_id,
          candidate_employee_id: c.employee_id,
          rank: c.rank,
        },
      });
    }
    setSelected(new Set());
  }

  function handleRespond(
    notificationId: number,
    response: "ACCEPTED" | "DECLINED" | "TIMEOUT" | "SKIPPED",
    rank?: number,
  ) {
    respondMutation.mutate(
      {
        calloutId: result.callout_id,
        notificationId,
        req: { response, rank, override_reason: "callout_outreach" },
      },
      {
        onSuccess: (data) => {
          if (data.deprioritized_employee_ids?.length) {
            setDeprioritized(new Set(data.deprioritized_employee_ids));
          }
          if (data.assigned_entry_id != null) {
            onAccepted(data.assigned_entry_id);
          }
        },
      },
    );
  }

  const selectedCount = selected.size;
  const remainingCount = uncontactedCandidates.length;

  return (
    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
      {/* Header */}
      <div className="border-b bg-muted/40 px-5 py-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Outreach Console</h3>
        <span className="text-xs text-muted-foreground">
          {notifications.length} attempt{notifications.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="p-5 space-y-5">
        {/* Active outreach */}
        {pendings.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Awaiting Response · {pendings.length}{" "}
              {pendings.length === 1 ? "candidate" : "candidates"}
            </p>
            <p className="text-xs text-muted-foreground -mt-1">
              First to accept takes the shift — the rest are auto-canceled.
            </p>
            {pendings.map((p) => (
              <PendingOutreachRow
                key={p.notification_id}
                notificationId={p.notification_id}
                employeeId={p.employee_id}
                candidateName={
                  candidatesByEmp.get(p.employee_id)?.name ?? p.employee_id
                }
                rank={candidatesByEmp.get(p.employee_id)?.rank}
                sentAt={p.created_at}
                disabled={respondMutation.isPending}
                onRespond={handleRespond}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed bg-muted/20 px-4 py-4 text-xs text-muted-foreground">
            No one being contacted right now. Pick staff below, then send to selected
            staff or everyone still available.
          </div>
        )}

        {/* History */}
        {notifications.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              History
            </p>
            <div className="space-y-1.5">
              {notifications.map((n) => {
                const filledByOther =
                  n.status === "CANCELED" &&
                  (n.payload_text ?? "")
                    .toLowerCase()
                    .includes(FILLED_BY_OTHER_MARKER);
                const style = filledByOther
                  ? FILLED_STYLE
                  : (STATUS_STYLE[n.status] ?? STATUS_STYLE.CANCELED);
                const Icon = style.icon;
                return (
                  <div
                    key={n.notification_id}
                    className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-xs"
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      {Icon && (
                        <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      )}
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-medium">
                            {candidatesByEmp.get(n.employee_id)?.name ??
                              n.employee_id}
                          </span>
                          {candidatesByEmp.get(n.employee_id) && (
                            <span className="text-muted-foreground">
                              #{candidatesByEmp.get(n.employee_id)!.rank}
                            </span>
                          )}
                          <Badge
                            variant="secondary"
                            className={cn(
                              "border text-[10px] px-1.5 py-0 h-4",
                              style.className,
                            )}
                          >
                            {style.label}
                          </Badge>
                        </div>
                        {filledByOther && n.payload_text && (
                          <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
                            {n.payload_text}
                          </div>
                        )}
                      </div>
                    </div>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {new Date(n.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Candidate queue */}
        {orderedCandidates.length > 0 && (
          <div className="space-y-3 border-t pt-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="shrink-0 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Queue
              </p>
              <div className="grid min-w-0 flex-1 grid-cols-2 gap-1.5 sm:flex sm:flex-none sm:items-center">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 min-w-0 px-2 text-[11px] gap-1"
                  onClick={() => handleSendBatch(Array.from(selected))}
                  disabled={
                    sendMutation.isPending ||
                    selectedCount === 0 ||
                    remainingCount === 0
                  }
                >
                  <Send className="h-3 w-3" />
                  <span className="truncate">Send selected ({selectedCount})</span>
                </Button>
                <Button
                  size="sm"
                  className="h-8 min-w-0 px-2 text-[11px] gap-1"
                  onClick={() => setConfirmAllOpen(true)}
                  disabled={sendMutation.isPending || remainingCount === 0}
                  title="Send outreach to every uncontacted candidate at once"
                >
                  <Users className="h-3 w-3" />
                  <span className="truncate">Send all ({remainingCount})</span>
                </Button>
              </div>
            </div>

            <div className="space-y-1.5">
              {orderedCandidates.map((c) => {
                const wasContacted = contacted.has(c.employee_id);
                const isDeprioritized = deprioritized.has(c.employee_id);
                const isSelected = selected.has(c.employee_id);
                return (
                  <label
                    key={c.employee_id}
                    className={cn(
                      "flex cursor-pointer items-center justify-between rounded-lg border px-3 py-2 text-xs transition-colors",
                      wasContacted
                        ? "bg-muted/30 cursor-default opacity-60"
                        : isSelected
                          ? "border-primary/30 bg-primary/5"
                          : "hover:bg-muted/30",
                      isDeprioritized && !wasContacted && "opacity-70",
                    )}
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 shrink-0 accent-primary"
                        checked={isSelected}
                        disabled={wasContacted || sendMutation.isPending}
                        onChange={() => toggleSelect(c.employee_id)}
                        aria-label={`Select ${c.name}`}
                      />
                      <div className="min-w-0">
                        <span className="font-medium">
                          #{c.rank} {c.name}
                        </span>
                        <span className="ml-1.5 text-muted-foreground">
                          {c.license}
                        </span>
                        {isDeprioritized && !wasContacted && (
                          <span className="ml-2 text-[10px] text-amber-700 font-medium">
                            Retry available
                          </span>
                        )}
                      </div>
                    </div>
                    {wasContacted && (
                      <span className="shrink-0 text-[10px] text-muted-foreground">
                        Contacted
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {respondMutation.isError && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {(respondMutation.error as Error)?.message ?? "Response failed."}
          </div>
        )}
      </div>

      <Dialog open={confirmAllOpen} onOpenChange={setConfirmAllOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Reach out to all {remainingCount} staff?
            </DialogTitle>
            <DialogDescription>
              This sends the outreach message to every uncontacted candidate at
              once. Whoever accepts first takes the shift — the rest are
              automatically canceled with a &ldquo;we found someone&rdquo;
              notice. Use this when the fill is urgent.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAllOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                handleSendBatch(
                  uncontactedCandidates.map((c) => c.employee_id),
                );
                setConfirmAllOpen(false);
              }}
            >
              Reach out to all {remainingCount}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface PendingOutreachRowProps {
  notificationId: number;
  employeeId: string;
  candidateName: string;
  rank?: number;
  sentAt: string;
  disabled: boolean;
  onRespond: (
    notificationId: number,
    response: "ACCEPTED" | "DECLINED" | "TIMEOUT" | "SKIPPED",
    rank?: number,
  ) => void;
}

function formatElapsed(sentAtMs: number, nowMs: number): string {
  const deltaSec = Math.max(0, Math.floor((nowMs - sentAtMs) / 1000));
  const ss = String(deltaSec % 60).padStart(2, "0");
  const totalMin = Math.floor(deltaSec / 60);
  if (totalMin < 60) {
    const mm = String(totalMin).padStart(2, "0");
    return `${mm}:${ss}`;
  }
  const hh = String(Math.floor(totalMin / 60)).padStart(2, "0");
  const mm = String(totalMin % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

function useElapsedLabel(sentAt: string): string {
  const sentAtMs = useMemo(() => new Date(sentAt).getTime(), [sentAt]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return formatElapsed(sentAtMs, now);
}

function PendingOutreachRow({
  notificationId,
  employeeId,
  candidateName,
  rank,
  sentAt,
  disabled,
  onRespond,
}: PendingOutreachRowProps) {
  const elapsedLabel = useElapsedLabel(sentAt);
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3">
      <div className="flex min-w-0 items-start gap-2.5">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-800">
          <Clock className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1 text-sm leading-snug">
          <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
            <span className="break-words font-medium">{candidateName}</span>
            <span className="shrink-0 tabular-nums text-xs font-medium text-amber-800">
              {elapsedLabel}
            </span>
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
            {rank && <span>#{rank}</span>}
            <span>{employeeId}</span>
          </div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-1.5">
        <Button
          size="sm"
          className="h-8 bg-emerald-600 px-2 text-xs gap-1 hover:bg-emerald-700"
          onClick={() => onRespond(notificationId, "ACCEPTED", rank)}
          disabled={disabled}
        >
          <CheckCircle2 className="h-3 w-3" />
          Accept
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-8 px-2 text-xs gap-1 border-red-200 text-red-700 hover:bg-red-50"
          onClick={() => onRespond(notificationId, "DECLINED", rank)}
          disabled={disabled}
        >
          <XCircle className="h-3 w-3" />
          Decline
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-8 px-2 text-xs"
          onClick={() => onRespond(notificationId, "SKIPPED", rank)}
          disabled={disabled}
        >
          Skip
        </Button>
      </div>
    </div>
  );
}
