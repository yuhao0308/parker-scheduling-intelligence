"use client";

import {
  useDeferredValue,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  BriefcaseMedical,
  Clock3,
  Gauge,
  GripHorizontal,
  PanelRightOpen,
  Search,
  Users,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useWorkHoursSnapshot } from "@/lib/queries";
import type { EmployeeWorkHours } from "@/lib/types";
import { useWorkHoursMonitor } from "@/providers/work-hours-provider";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const STATUS_STYLES = {
  healthy: {
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    bar: "bg-emerald-500",
    label: "On track",
  },
  near_ot: {
    badge: "bg-amber-50 text-amber-800 ring-amber-200",
    bar: "bg-amber-500",
    label: "Near OT",
  },
  overtime: {
    badge: "bg-orange-50 text-orange-800 ring-orange-200",
    bar: "bg-orange-500",
    label: "At OT",
  },
  high_ot: {
    badge: "bg-rose-50 text-rose-800 ring-rose-200",
    bar: "bg-rose-500",
    label: "Over OT",
  },
} as const;

const WINDOW_MARGIN = 24;
const HEADER_HEIGHT = 148;
const DESKTOP_MIN_WIDTH = 360;
const DESKTOP_DEFAULT_WIDTH = 440;
const MOBILE_MIN_WIDTH = 320;
const MOBILE_DEFAULT_WIDTH = 360;
const RESIZE_HANDLE_WIDTH = 10;

function moveMonth(year: number, month: number, delta: number) {
  const next = new Date(year, month - 1 + delta, 1);
  return {
    year: next.getFullYear(),
    month: next.getMonth() + 1,
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function clampPercent(value: number) {
  return clamp(value, 0, 100);
}

function cycleBarStatus(employee: EmployeeWorkHours): keyof typeof STATUS_STYLES {
  if (employee.license === "RN") {
    if (employee.current_cycle_shifts >= 12) return "high_ot";
    if (employee.current_cycle_shifts >= 10) return "overtime";
    if (employee.current_cycle_shifts >= 9) return "near_ot";
    return "healthy";
  }
  if (employee.current_cycle_hours >= 62.5) return "high_ot";
  if (employee.current_cycle_hours > 37.5) return "overtime";
  if (employee.current_cycle_hours >= 29.25) return "near_ot";
  return "healthy";
}

function mixPercent(value: number, total: number) {
  if (!total) return 0;
  return clampPercent((value / total) * 100);
}

function getViewportLimits() {
  if (typeof window === "undefined") {
    return {
      maxHeight: 860,
      minWidth: DESKTOP_MIN_WIDTH,
      maxWidth: 520,
      defaultWidth: DESKTOP_DEFAULT_WIDTH,
    };
  }

  const isCompact = window.innerWidth < 1024;
  const horizontalBudget = window.innerWidth - WINDOW_MARGIN * 2;

  const minWidth = isCompact ? MOBILE_MIN_WIDTH : DESKTOP_MIN_WIDTH;
  const maxWidth = isCompact
    ? Math.min(horizontalBudget, 520)
    : Math.min(horizontalBudget, Math.round(window.innerWidth / 3));
  const defaultWidth = clamp(
    isCompact ? MOBILE_DEFAULT_WIDTH : DESKTOP_DEFAULT_WIDTH,
    minWidth,
    maxWidth,
  );

  return {
    maxHeight: Math.min(window.innerHeight - WINDOW_MARGIN * 2, 860),
    minWidth,
    maxWidth,
    defaultWidth,
  };
}

function getDefaultFrame() {
  const limits = getViewportLimits();

  if (typeof window === "undefined") {
    return {
      height: limits.maxHeight,
      width: limits.defaultWidth,
      x: WINDOW_MARGIN,
      y: WINDOW_MARGIN,
    };
  }

  return {
    height: limits.maxHeight,
    width: limits.defaultWidth,
    x: Math.max(WINDOW_MARGIN, window.innerWidth - limits.defaultWidth - WINDOW_MARGIN),
    y: Math.max(WINDOW_MARGIN, Math.round((window.innerHeight - limits.maxHeight) / 2)),
  };
}

function workloadSearchMatch(employee: EmployeeWorkHours, search: string) {
  if (!search) return true;

  const haystack = [
    employee.name,
    employee.employee_id,
    employee.license,
    employee.employment_class,
    employee.home_unit_id ?? "",
    employee.primary_unit_id ?? "",
    employee.scheduled_unit_ids.join(" "),
  ]
    .join(" ")
    .toLowerCase();

  return haystack.includes(search.toLowerCase());
}

function cycleFillPercent(employee: EmployeeWorkHours) {
  if (employee.license === "RN") {
    return clampPercent((employee.current_cycle_shifts / 12) * 100);
  }
  return clampPercent((employee.current_cycle_hours / 62.5) * 100);
}

function cycleThresholdPercent(employee: EmployeeWorkHours) {
  if (employee.license === "RN") {
    return (10 / 12) * 100;
  }
  return (37.5 / 62.5) * 100;
}

function getPeakLoadLabel(employee: EmployeeWorkHours) {
  if (employee.license === "RN") {
    return `${employee.peak_biweekly_shifts} shifts busiest cycle`;
  }
  return `${employee.peak_week_hours.toFixed(1)}h busiest week`;
}

function getProjectedRiskLabel(employee: EmployeeWorkHours) {
  if (employee.license === "RN") {
    let label = `${employee.projected_overtime_shifts} OT shift${employee.projected_overtime_shifts === 1 ? "" : "s"}`;
    if (employee.double_shift_days > 0) {
      label += `, ${employee.double_shift_days} dbl-shift day${employee.double_shift_days === 1 ? "" : "s"}`;
    }
    return label;
  }
  return `${employee.projected_overtime_hours.toFixed(1)} OT hours`;
}

function SummaryCard({
  icon: Icon,
  label,
  value,
  sublabel,
  accentClassName,
}: {
  icon: typeof Users;
  label: string;
  value: string;
  sublabel: string;
  accentClassName: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/88 p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
            {label}
          </div>
          <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
            {value}
          </div>
          <div className="mt-1 text-sm leading-5 text-muted-foreground">{sublabel}</div>
        </div>
        <div
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-2xl ring-1",
            accentClassName,
          )}
        >
          <Icon className="size-4" />
        </div>
      </div>
    </div>
  );
}

function MetricTile({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/92 p-3">
      <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1.5 text-xl font-semibold tracking-tight text-slate-950">
        {value}
      </div>
      <div className="mt-1 text-sm leading-5 text-muted-foreground">{detail}</div>
    </div>
  );
}

function EmployeeCard({ employee }: { employee: EmployeeWorkHours }) {
  const status = STATUS_STYLES[employee.overtime_status];
  const currentCycleValue =
    employee.license === "RN"
      ? `${employee.current_cycle_shifts} shifts`
      : `${employee.current_cycle_hours.toFixed(1)}h`;

  return (
    <article className="rounded-[26px] border border-slate-200/80 bg-white/88 p-4 shadow-sm">
      {/* Identity header */}
      <div className="min-w-0">
        <h3 className="truncate text-lg font-semibold tracking-tight text-slate-950">
          {employee.name}
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {employee.employee_id} • Home {employee.home_unit_id ?? "Unassigned"}
        </p>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Badge variant="outline">{employee.license}</Badge>
        <Badge variant="outline">{employee.employment_class}</Badge>
        {employee.primary_unit_id ? (
          <Badge variant="outline">Primary {employee.primary_unit_id}</Badge>
        ) : null}
        {employee.callout_count > 0 ? (
          <Badge
            className="bg-red-50 text-red-700 ring-1 ring-red-200"
            variant="secondary"
          >
            {employee.callout_count} callout{employee.callout_count === 1 ? "" : "s"}
          </Badge>
        ) : null}
      </div>

      {/* Schedule Projection section */}
      <div className="mt-4 rounded-2xl border border-indigo-100/80 bg-indigo-50/30 p-3.5">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-500">
            Schedule Projection
          </div>
          <Badge className={cn("shrink-0 ring-1", status.badge)} variant="secondary">
            {status.label}
          </Badge>
        </div>

        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {employee.overtime_detail}
        </p>

        <div className="mt-3 rounded-2xl border border-slate-200/60 bg-white/85 p-3.5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-slate-900">Home vs float mix</div>
            <div className="font-mono text-sm text-slate-600">
              {employee.home_unit_shifts}/{employee.float_shifts}
            </div>
          </div>
          <div className="mt-3 relative h-2.5 overflow-hidden rounded-full bg-slate-200">
            <div
              className="absolute inset-y-0 left-0 bg-teal-500"
              style={{
                width: `${mixPercent(employee.home_unit_shifts, employee.scheduled_shifts)}%`,
              }}
            />
            <div
              className="absolute inset-y-0 bg-amber-400"
              style={{
                left: `${mixPercent(employee.home_unit_shifts, employee.scheduled_shifts)}%`,
                width: `${mixPercent(employee.float_shifts, employee.scheduled_shifts)}%`,
              }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] uppercase tracking-[0.14em] text-slate-500">
            <span>{employee.home_unit_shifts} home</span>
            <span>{employee.float_shifts} float</span>
          </div>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <MetricTile
            label="Selected Month"
            value={`${employee.scheduled_hours.toFixed(1)}h`}
            detail={`${employee.scheduled_shifts} scheduled shifts`}
          />
          <MetricTile
            label="Peak Load"
            value={getPeakLoadLabel(employee)}
            detail={getProjectedRiskLabel(employee)}
          />
          <MetricTile
            label="Unit Spread"
            value={`${employee.scheduled_unit_ids.length} unit${employee.scheduled_unit_ids.length === 1 ? "" : "s"}`}
            detail={
              employee.scheduled_unit_ids.length > 0
                ? employee.scheduled_unit_ids.join(", ")
                : "No assignments in this month"
            }
          />
        </div>
      </div>

      {/* Current Actuals section */}
      <div className="mt-3 rounded-2xl border border-emerald-100/80 bg-emerald-50/30 p-3.5">
        <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-slate-500">
          Current Actuals
        </div>

        <div className="mt-2 flex items-center justify-between gap-3">
          <div className="text-sm font-medium text-slate-900">Cycle load</div>
          <div className="font-mono text-sm text-slate-600">{currentCycleValue}</div>
        </div>
        <div className="mt-2 relative h-2.5 overflow-hidden rounded-full bg-slate-200">
          <div
            className={cn("h-full rounded-full", STATUS_STYLES[cycleBarStatus(employee)].bar)}
            style={{ width: `${cycleFillPercent(employee)}%` }}
          />
          <div
            className="absolute inset-y-0 w-px bg-slate-500/70"
            style={{ left: `${cycleThresholdPercent(employee)}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] uppercase tracking-[0.14em] text-slate-500">
          <span>{employee.license === "RN" ? "RN biweekly OT marker" : "37.5h OT marker"}</span>
          <span>
            {employee.license === "RN"
              ? `${employee.current_cycle_hours.toFixed(1)}h in ledger`
              : `${employee.current_cycle_shifts} shifts in ledger`}
          </span>
        </div>
      </div>
    </article>
  );
}

export function WorkHoursMonitor() {
  const { open, setOpen, scope, setScope } = useWorkHoursMonitor();
  const initialFrame = getDefaultFrame();
  const [panelWidth, setPanelWidth] = useState(initialFrame.width);
  const [panelHeight, setPanelHeight] = useState(initialFrame.height);
  const [{ x, y }, setPosition] = useState({ x: initialFrame.x, y: initialFrame.y });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const dragState = useRef<
    | {
        kind: "move";
        offsetX: number;
        offsetY: number;
        pointerId: number;
      }
    | {
        kind: "resize";
        originX: number;
        originWidth: number;
        originLeft: number;
        pointerId: number;
      }
    | null
  >(null);

  const deferredSearch = useDeferredValue(search);
  const { data, isLoading, isError, error } = useWorkHoursSnapshot(
    scope.year,
    scope.month,
    open,
  );

  const filteredEmployees =
    data?.employees.filter((employee) => {
      if (!workloadSearchMatch(employee, deferredSearch)) {
        return false;
      }
      if (statusFilter === "all") {
        return true;
      }
      if (statusFilter === "watch") {
        return employee.overtime_status === "near_ot";
      }
      return employee.overtime_status === statusFilter;
    }) ?? [];

  useEffect(() => {
    if (!open) return;

    const syncToViewport = () => {
      const limits = getViewportLimits();
      setPanelHeight(limits.maxHeight);
      setPanelWidth((current) => clamp(current, limits.minWidth, limits.maxWidth));
      setPosition((current) => {
        const nextWidth = clamp(panelWidth, limits.minWidth, limits.maxWidth);
        const maxX = Math.max(WINDOW_MARGIN, window.innerWidth - nextWidth - WINDOW_MARGIN);
        const maxY = Math.max(WINDOW_MARGIN, window.innerHeight - limits.maxHeight - WINDOW_MARGIN);
        return {
          x: clamp(current.x, WINDOW_MARGIN, maxX),
          y: clamp(current.y, WINDOW_MARGIN, maxY),
        };
      });
    };

    syncToViewport();
    window.addEventListener("resize", syncToViewport);
    return () => window.removeEventListener("resize", syncToViewport);
  }, [open, panelWidth]);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, setOpen]);

  function handleMoveStart(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;

    dragState.current = {
      kind: "move",
      offsetX: event.clientX - x,
      offsetY: event.clientY - y,
      pointerId: event.pointerId,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleResizeStart(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === "mouse" && event.button !== 0) return;

    dragState.current = {
      kind: "resize",
      originLeft: x,
      originWidth: panelWidth,
      originX: event.clientX,
      pointerId: event.pointerId,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragState.current || dragState.current.pointerId !== event.pointerId) {
      return;
    }

    const limits = getViewportLimits();

    if (dragState.current.kind === "move") {
      const nextX = event.clientX - dragState.current.offsetX;
      const nextY = event.clientY - dragState.current.offsetY;
      const maxX = Math.max(WINDOW_MARGIN, window.innerWidth - panelWidth - WINDOW_MARGIN);
      const maxY = Math.max(WINDOW_MARGIN, window.innerHeight - panelHeight - WINDOW_MARGIN);

      setPosition({
        x: clamp(nextX, WINDOW_MARGIN, maxX),
        y: clamp(nextY, WINDOW_MARGIN, maxY),
      });
      return;
    }

    const deltaX = dragState.current.originX - event.clientX;
    const nextWidth = clamp(
      dragState.current.originWidth + deltaX,
      limits.minWidth,
      limits.maxWidth,
    );
    const nextLeft = clamp(
      dragState.current.originLeft - (nextWidth - dragState.current.originWidth),
      WINDOW_MARGIN,
      window.innerWidth - nextWidth - WINDOW_MARGIN,
    );

    setPanelWidth(nextWidth);
    setPosition((current) => ({
      x: nextLeft,
      y: clamp(
        current.y,
        WINDOW_MARGIN,
        Math.max(WINDOW_MARGIN, window.innerHeight - panelHeight - WINDOW_MARGIN),
      ),
    }));
  }

  function handlePointerEnd(event: ReactPointerEvent<HTMLDivElement>) {
    if (!dragState.current || dragState.current.pointerId !== event.pointerId) {
      return;
    }
    dragState.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  }

  return (
    <>
      <Button
        className="fixed left-6 bottom-6 z-40 h-12 rounded-2xl border border-slate-300/70 bg-white/95 px-4 text-slate-900 shadow-lg shadow-slate-900/10 hover:bg-slate-50"
        variant="outline"
        onClick={() => setOpen(true)}
      >
        <PanelRightOpen className="size-4" />
        Workload Monitor
      </Button>

      {open ? (
        <div
          className="fixed z-50 overflow-hidden rounded-[28px] border border-slate-300/70 bg-white/88 shadow-2xl shadow-slate-900/15 backdrop-blur-[6px]"
          style={{
            height: `${panelHeight}px`,
            width: `${panelWidth}px`,
            left: `${x}px`,
            top: `${y}px`,
          }}
        >
          <div
            className="absolute top-0 left-0 z-20 h-full cursor-ew-resize"
            style={{ width: `${RESIZE_HANDLE_WIDTH}px` }}
            onPointerDown={handleResizeStart}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerEnd}
            onPointerCancel={handlePointerEnd}
          />

          <div className="border-b border-white/10 bg-[linear-gradient(145deg,rgba(15,23,42,0.97),rgba(30,41,59,0.95)_58%,rgba(13,148,136,0.82))] text-white">
            <div className="flex items-start justify-between gap-4 px-5 py-5">
              <div
                className="min-w-0 flex-1 cursor-grab space-y-2 active:cursor-grabbing"
                onPointerDown={handleMoveStart}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerEnd}
                onPointerCancel={handlePointerEnd}
              >
                <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-white/75">
                  <GripHorizontal className="size-3.5" />
                  Drag Window
                </div>
                <div className="text-[28px] font-semibold tracking-tight text-white">
                  Workload Monitor
                </div>
                <div className="max-w-md text-sm leading-6 text-white/72">
                  Resize from the left edge. Drag the header to reposition. This panel is optimized for a narrow side-window view.
                </div>
              </div>

              <div className="flex shrink-0 items-start gap-2">
                <div className="rounded-2xl bg-white/10 p-1">
                  <div className="flex items-center gap-1 text-white">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-white hover:bg-white/15 hover:text-white"
                      onClick={() =>
                        setScope((current) => moveMonth(current.year, current.month, -1))
                      }
                    >
                      <ArrowLeft className="size-4" />
                    </Button>
                    <div className="min-w-32 px-2 text-center text-sm font-medium">
                      {MONTH_NAMES[scope.month - 1]} {scope.year}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-white hover:bg-white/15 hover:text-white"
                      onClick={() =>
                        setScope((current) => moveMonth(current.year, current.month, 1))
                      }
                    >
                      <ArrowRight className="size-4" />
                    </Button>
                  </div>
                </div>

                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-white hover:bg-white/15 hover:text-white"
                  onClick={() => setOpen(false)}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>
          </div>

          <div
            className="overflow-y-auto bg-[radial-gradient(circle_at_top,rgba(15,118,110,0.07),transparent_28%),linear-gradient(180deg,rgba(248,250,252,0.78),rgba(255,255,255,0.95))]"
            style={{ height: `${panelHeight - HEADER_HEIGHT}px` }}
          >
            <div className="space-y-5 px-4 py-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <SummaryCard
                  icon={BriefcaseMedical}
                  label="Scheduled Hours"
                  value={`${data?.summary.total_scheduled_hours.toFixed(0) ?? "0"}h`}
                  sublabel={`${data?.summary.average_scheduled_hours.toFixed(1) ?? "0.0"}h average`}
                  accentClassName="bg-teal-50 text-teal-700 ring-teal-200"
                />
                <SummaryCard
                  icon={Users}
                  label="Employees"
                  value={`${data?.summary.employee_count ?? 0}`}
                  sublabel={`${filteredEmployees.length} visible now`}
                  accentClassName="bg-slate-100 text-slate-700 ring-slate-200"
                />
                <SummaryCard
                  icon={Gauge}
                  label="OT Watch"
                  value={`${(data?.summary.employees_near_ot ?? 0) + (data?.summary.employees_in_ot ?? 0) + (data?.summary.employees_high_ot ?? 0)}`}
                  sublabel={`${data?.summary.employees_in_ot ?? 0} at OT, ${data?.summary.employees_high_ot ?? 0} over OT`}
                  accentClassName="bg-amber-50 text-amber-700 ring-amber-200"
                />
                <SummaryCard
                  icon={Clock3}
                  label="Covering Other Units"
                  value={`${data?.summary.total_float_shifts ?? 0}`}
                  sublabel="Shifts outside home unit"
                  accentClassName="bg-cyan-50 text-cyan-700 ring-cyan-200"
                />
              </div>

              <div className="rounded-[24px] border border-slate-200/80 bg-white/86 p-4 shadow-sm">
                <div className="space-y-3">
                  <label className="relative block">
                    <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      className="h-10 rounded-xl bg-white pl-9"
                      placeholder="Search name, ID, unit, role..."
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </label>
                  <select
                    className="h-10 w-full rounded-xl border border-input bg-white px-3 text-sm"
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value)}
                  >
                    <option value="all">All statuses</option>
                    <option value="watch">Near OT</option>
                    <option value="overtime">At OT</option>
                    <option value="high_ot">Over OT</option>
                    <option value="healthy">On track</option>
                  </select>
                  <div className="rounded-2xl bg-slate-50 px-3 py-2.5 text-sm leading-6 text-muted-foreground">
                    OT markers combine selected-month assignments with the latest synced ledger data.
                  </div>
                </div>
              </div>

              {isLoading ? (
                <div className="rounded-[24px] border border-slate-200/80 bg-white/88 p-10 text-center text-muted-foreground shadow-sm">
                  Loading workload snapshot...
                </div>
              ) : isError ? (
                <div className="rounded-[24px] border border-destructive/30 bg-red-50 p-10 text-center text-destructive shadow-sm">
                  {error.message}
                </div>
              ) : filteredEmployees.length === 0 ? (
                <div className="rounded-[24px] border border-slate-200/80 bg-white/88 p-10 text-center text-muted-foreground shadow-sm">
                  No employees match the current filters.
                </div>
              ) : (
                <div className="space-y-4">
                  {filteredEmployees.map((employee) => (
                    <EmployeeCard key={employee.employee_id} employee={employee} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
