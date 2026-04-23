"use client";

import { ArrowRight, UserCheck, UserX, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useRecentCallouts } from "@/lib/queries";
import { cn } from "@/lib/utils";
import type { RecentCallout } from "@/lib/types";

const licenseBadgeClass: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800 border-blue-200",
  LPN: "bg-green-100 text-green-800 border-green-200",
  CNA: "bg-amber-100 text-amber-800 border-amber-200",
  PCT: "bg-purple-100 text-purple-800 border-purple-200",
};

const shiftBadgeClass: Record<string, string> = {
  DAY: "bg-amber-50 text-amber-900 border-amber-200",
  EVENING: "bg-orange-50 text-orange-900 border-orange-200",
  NIGHT: "bg-slate-100 text-slate-800 border-slate-200",
};

export default function DashboardPage() {
  const { data: callouts, isLoading, isError, error } = useRecentCallouts();

  const totalCallouts = callouts?.length ?? 0;
  const filledCount =
    callouts?.filter((c) => c.selected_employee_id !== null).length ?? 0;
  const resolvedCount =
    callouts?.filter((c) => c.selected_rank !== null).length ?? 0;
  const overrideCount =
    callouts?.filter(
      (c) => c.selected_rank !== null && c.selected_rank !== 1,
    ).length ?? 0;
  const overrideRate =
    resolvedCount > 0
      ? Math.round((overrideCount / resolvedCount) * 100)
      : 0;

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Recent call-outs and how they were resolved.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Recent Callouts" value={totalCallouts} />
        <StatCard
          label="Replacements Filled"
          value={filledCount}
          sub={
            totalCallouts > 0
              ? `${filledCount} of ${totalCallouts}`
              : undefined
          }
        />
        <StatCard
          label="Override Rate"
          value={`${overrideRate}%`}
          sub={
            resolvedCount > 0
              ? `${overrideCount} of ${resolvedCount} resolved`
              : "no decisions yet"
          }
          hint="How often coordinators picked a candidate other than the top AI recommendation."
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Call-Outs</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              Loading…
            </div>
          ) : isError ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" />
              {error.message}
            </div>
          ) : !callouts || callouts.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">
              No callouts recorded yet.
            </div>
          ) : (
            <ul className="divide-y">
              {callouts.map((c) => (
                <CalloutRow key={c.callout_id} callout={c} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  hint,
}: {
  label: string;
  value: string | number;
  sub?: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle
          className="text-sm text-muted-foreground font-normal"
          title={hint}
        >
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="text-3xl font-bold tabular-nums">{value}</div>
        {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function PersonPill({
  name,
  employeeId,
  license,
  tone,
}: {
  name: string | null;
  employeeId: string;
  license: string | null;
  tone: "called-out" | "replacement";
}) {
  const Icon = tone === "called-out" ? UserX : UserCheck;
  const iconWrap =
    tone === "called-out"
      ? "bg-rose-100 text-rose-700"
      : "bg-emerald-100 text-emerald-700";
  const displayName = name ?? employeeId;
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          iconWrap,
        )}
      >
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-medium truncate">{displayName}</span>
          {license && (
            <Badge
              variant="secondary"
              className={cn(
                "border text-[10px] px-1.5 py-0 font-semibold",
                licenseBadgeClass[license] ?? "",
              )}
            >
              {license}
            </Badge>
          )}
        </div>
        <div className="font-mono text-[10px] text-muted-foreground">
          {employeeId}
        </div>
      </div>
    </div>
  );
}

function UnfilledPill() {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <AlertCircle className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0">
        <div className="text-sm font-medium text-muted-foreground">
          Not yet assigned
        </div>
        <div className="text-[10px] text-muted-foreground">
          awaiting outreach
        </div>
      </div>
    </div>
  );
}

function CalloutRow({ callout: c }: { callout: RecentCallout }) {
  const isOverride = c.selected_rank !== null && c.selected_rank !== 1;
  const isTopPick = c.selected_rank === 1;

  return (
    <li
      className={cn(
        "grid grid-cols-[auto_1fr_auto_1fr_auto] items-center gap-4 px-5 py-3.5 transition-colors hover:bg-muted/30",
        isOverride && "bg-amber-50/40",
      )}
    >
      {/* Date + shift */}
      <div className="min-w-[6.5rem]">
        <div className="text-sm font-medium tabular-nums">{c.shift_date}</div>
        <div className="mt-0.5 flex items-center gap-1.5">
          <Badge
            variant="outline"
            className={cn(
              "text-[10px] px-1.5 py-0 font-semibold",
              shiftBadgeClass[c.shift_label] ?? "",
            )}
          >
            {c.shift_label}
          </Badge>
          <span className="text-[11px] text-muted-foreground truncate max-w-[10rem]">
            {c.unit_name ?? c.unit_id}
          </span>
        </div>
      </div>

      {/* Called out */}
      <PersonPill
        name={c.employee_name}
        employeeId={c.employee_id}
        license={c.employee_license}
        tone="called-out"
      />

      {/* Arrow */}
      <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

      {/* Replacement */}
      <div className="min-w-0">
        {c.selected_employee_id ? (
          <PersonPill
            name={c.selected_employee_name}
            employeeId={c.selected_employee_id}
            license={c.selected_employee_license}
            tone="replacement"
          />
        ) : (
          <UnfilledPill />
        )}
      </div>

      {/* Pick / override indicator */}
      <div className="flex flex-col items-end gap-1 min-w-[7rem]">
        {isTopPick && (
          <Badge className="bg-emerald-100 text-emerald-800 border border-emerald-200 text-[10px] px-2 py-0 font-semibold">
            Top Pick
          </Badge>
        )}
        {isOverride && (
          <Badge className="bg-amber-100 text-amber-800 border border-amber-200 text-[10px] px-2 py-0 font-semibold">
            Override · #{c.selected_rank}
          </Badge>
        )}
        {isOverride && c.override_reason && (
          <span
            className="text-[11px] text-muted-foreground max-w-[12rem] truncate text-right"
            title={c.override_reason}
          >
            {c.override_reason}
          </span>
        )}
      </div>
    </li>
  );
}
