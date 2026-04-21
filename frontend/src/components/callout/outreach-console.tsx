"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  useDemoConfig,
  useOutreach,
  useRespondOutreach,
  useSendOutreach,
} from "@/lib/queries";
import type { CalloutResponse, ScoredCandidate } from "@/lib/types";

const FILLED_BY_OTHER_MARKER = "filled by another teammate";

const STATUS_BADGE: Record<string, string> = {
  SENT: "bg-amber-100 text-amber-800",
  ACCEPTED: "bg-emerald-100 text-emerald-800",
  DECLINED: "bg-red-100 text-red-800",
  TIMEOUT: "bg-slate-100 text-slate-700",
  SKIPPED: "bg-slate-100 text-slate-700",
  CANCELED: "bg-slate-100 text-slate-500 line-through",
};

// Distinct badge for sibling outreach canceled because ACCEPTED elsewhere.
const FILLED_BADGE = "bg-teal-100 text-teal-800";

interface OutreachConsoleProps {
  result: CalloutResponse;
  onAccepted: (assignedEntryId: number) => void;
}

export function OutreachConsole({ result, onAccepted }: OutreachConsoleProps) {
  const { data: notifications = [] } = useOutreach(result.callout_id);
  const { data: demoConfig } = useDemoConfig();
  const sendMutation = useSendOutreach();
  const respondMutation = useRespondOutreach();

  // Cumulative deprioritized set — grows when respondOutreach returns
  // `deprioritized_employee_ids` for TIMEOUT/DECLINED replies. Pushes those
  // candidates to the bottom of the queue but doesn't remove them (supervisor
  // spec: 15m-timeout keeps them eligible, just lower priority).
  const [deprioritized, setDeprioritized] = useState<Set<string>>(new Set());

  const outreachTimeoutSeconds = demoConfig?.outreach_timeout_seconds ?? 15;
  const outreachTimeoutLabel = demoConfig?.outreach_timeout_label ?? "15 minutes";

  const candidatesByEmp = useMemo(() => {
    const m = new Map<string, ScoredCandidate>();
    for (const c of result.candidates) m.set(c.employee_id, c);
    return m;
  }, [result.candidates]);

  const contacted = new Set(notifications.map((n) => n.employee_id));
  const pending = notifications.find((n) => n.status === "SENT");

  // Re-ordered candidate queue: remaining first, deprioritized at bottom.
  const orderedCandidates = useMemo(() => {
    const remaining: ScoredCandidate[] = [];
    const bottom: ScoredCandidate[] = [];
    for (const c of result.candidates) {
      if (deprioritized.has(c.employee_id)) bottom.push(c);
      else remaining.push(c);
    }
    return [...remaining, ...bottom];
  }, [result.candidates, deprioritized]);

  const nextCandidate = orderedCandidates.find(
    (c) => !contacted.has(c.employee_id),
  );

  function handleSend(candidate: ScoredCandidate) {
    sendMutation.mutate({
      calloutId: result.callout_id,
      req: {
        recommendation_log_id: result.recommendation_log_id,
        candidate_employee_id: candidate.employee_id,
        rank: candidate.rank,
      },
    });
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

  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Outreach console</h3>
          <span className="text-xs text-muted-foreground">
            {notifications.length} attempt(s)
          </span>
        </div>

        {pending ? (
          <PendingOutreachRow
            notificationId={pending.notification_id}
            employeeId={pending.employee_id}
            candidateName={
              candidatesByEmp.get(pending.employee_id)?.name ?? pending.employee_id
            }
            rank={candidatesByEmp.get(pending.employee_id)?.rank}
            disabled={respondMutation.isPending}
            onRespond={handleRespond}
            timeoutSeconds={outreachTimeoutSeconds}
            timeoutLabel={outreachTimeoutLabel}
          />
        ) : (
          <div className="text-xs text-muted-foreground">
            No active outreach. Use &quot;Send&quot; on a candidate below to start.
            Timeout is{" "}
            <span className="font-medium">{outreachTimeoutLabel}</span> — expired
            candidates move to the bottom of the queue.
          </div>
        )}

        {notifications.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs font-semibold text-muted-foreground">
              History
            </div>
            {notifications.map((n) => {
              const filledByOther =
                n.status === "CANCELED" &&
                (n.payload_text ?? "").toLowerCase().includes(
                  FILLED_BY_OTHER_MARKER,
                );
              const badgeClass = filledByOther
                ? FILLED_BADGE
                : (STATUS_BADGE[n.status] ?? "bg-slate-100");
              const badgeLabel = filledByOther ? "WE FOUND SOMEONE" : n.status;
              return (
                <div
                  key={n.notification_id}
                  className="flex items-start justify-between text-xs border rounded-md px-2 py-1 gap-2"
                >
                  <div className="flex items-start gap-2 min-w-0">
                    <Badge className={badgeClass}>{badgeLabel}</Badge>
                    <div className="min-w-0">
                      <div>
                        {candidatesByEmp.get(n.employee_id)?.name ??
                          n.employee_id}
                        {candidatesByEmp.get(n.employee_id) && (
                          <span className="text-muted-foreground ml-1">
                            (#{candidatesByEmp.get(n.employee_id)!.rank})
                          </span>
                        )}
                      </div>
                      {filledByOther && n.payload_text && (
                        <div className="text-[10px] text-muted-foreground mt-0.5 truncate">
                          {n.payload_text}
                        </div>
                      )}
                    </div>
                  </div>
                  <span className="text-muted-foreground shrink-0">
                    {new Date(n.created_at).toLocaleTimeString()}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Candidate queue — ordered so deprioritized (greyed) sit at the bottom */}
        {!pending && orderedCandidates.length > 0 && (
          <div className="border-t pt-3 space-y-1">
            <div className="text-xs font-semibold text-muted-foreground">
              Candidate queue
            </div>
            {orderedCandidates.map((c) => {
              const wasContacted = contacted.has(c.employee_id);
              const isDeprioritized = deprioritized.has(c.employee_id);
              return (
                <div
                  key={c.employee_id}
                  className={cn(
                    "flex items-center justify-between text-xs border rounded-md px-2 py-1",
                    isDeprioritized && "opacity-60",
                  )}
                >
                  <div className="min-w-0">
                    <span className="font-medium">
                      #{c.rank} {c.name}
                    </span>
                    <span className="text-muted-foreground ml-1">
                      ({c.license})
                    </span>
                    {isDeprioritized && (
                      <span className="ml-2 text-[10px] text-amber-800">
                        Retry available
                      </span>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant={c === nextCandidate ? "default" : "outline"}
                    className="h-6 px-2 text-[11px]"
                    onClick={() => handleSend(c)}
                    disabled={sendMutation.isPending || wasContacted}
                  >
                    {wasContacted ? "Contacted" : "Send"}
                  </Button>
                </div>
              );
            })}
          </div>
        )}

        {respondMutation.isError && (
          <div className="text-xs text-destructive">
            {(respondMutation.error as Error)?.message ?? "Response failed."}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface PendingOutreachRowProps {
  notificationId: number;
  employeeId: string;
  candidateName: string;
  rank?: number;
  disabled: boolean;
  onRespond: (
    notificationId: number,
    response: "ACCEPTED" | "DECLINED" | "TIMEOUT" | "SKIPPED",
    rank?: number,
  ) => void;
  timeoutSeconds: number;
  timeoutLabel: string;
}

function PendingOutreachRow({
  notificationId,
  employeeId,
  candidateName,
  rank,
  disabled,
  onRespond,
  timeoutSeconds,
  timeoutLabel,
}: PendingOutreachRowProps) {
  const [remaining, setRemaining] = useState(timeoutSeconds);
  const [fired, setFired] = useState(false);

  useEffect(() => {
    setRemaining(timeoutSeconds);
    setFired(false);
    const start = Date.now();
    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - start) / 1000);
      const next = Math.max(0, timeoutSeconds - elapsed);
      setRemaining(next);
      if (next === 0) {
        clearInterval(interval);
      }
    }, 250);
    return () => clearInterval(interval);
  }, [notificationId, timeoutSeconds]);

  useEffect(() => {
    if (remaining === 0 && !fired) {
      setFired(true);
      onRespond(notificationId, "TIMEOUT", rank);
    }
  }, [remaining, fired, notificationId, onRespond, rank]);

  return (
    <div className="flex items-center justify-between border rounded-md px-3 py-2 bg-amber-50 border-amber-200">
      <div className="text-sm">
        Waiting on{" "}
        <span className="font-medium">
          {candidateName}
          {rank && <span className="text-muted-foreground"> (#{rank})</span>}
        </span>{" "}
        <span className="text-xs text-muted-foreground">({employeeId})</span>
      </div>
      <div className="flex items-center gap-2">
        <span
          className="text-[11px] text-muted-foreground tabular-nums"
          title={`Auto-timeout in ${timeoutLabel} (demo: ${remaining}s)`}
        >
          {remaining}s
        </span>
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onRespond(notificationId, "ACCEPTED", rank)}
          disabled={disabled}
        >
          Accept
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs text-red-700 border-red-200 hover:bg-red-50"
          onClick={() => onRespond(notificationId, "DECLINED", rank)}
          disabled={disabled}
        >
          Decline
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={() => onRespond(notificationId, "SKIPPED", rank)}
          disabled={disabled}
        >
          Skip
        </Button>
      </div>
    </div>
  );
}
