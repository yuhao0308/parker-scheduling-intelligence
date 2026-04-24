"use client";

import {
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  PanelRightOpen,
  PhoneOff,
  Search,
  TrendingUp,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useWorkHoursSnapshot } from "@/lib/queries";
import type { EmployeeWorkHours, LicenseType } from "@/lib/types";
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

// OT thresholds — mirror app/services/overtime.py
const WEEKLY_OT_HOURS = 37.5;
const HIGH_OT_HOURS = 62.5;
const RN_BIWEEKLY_OT_SHIFTS = 10; // 11th shift triggers OT
const RN_HIGH_OT_SHIFTS = 12;

type OvertimeStatus = EmployeeWorkHours["overtime_status"];

const STATUS_META: Record<
  OvertimeStatus,
  { label: string; dot: string; chipOn: string; bar: string; text: string }
> = {
  healthy: {
    label: "Healthy",
    dot: "bg-emerald-500",
    chipOn: "bg-emerald-600 text-white border-emerald-600",
    bar: "bg-emerald-500",
    text: "text-emerald-700",
  },
  near_ot: {
    label: "Watch",
    dot: "bg-amber-500",
    chipOn: "bg-amber-600 text-white border-amber-600",
    bar: "bg-amber-500",
    text: "text-amber-700",
  },
  overtime: {
    label: "OT",
    dot: "bg-orange-500",
    chipOn: "bg-orange-600 text-white border-orange-600",
    bar: "bg-orange-500",
    text: "text-orange-700",
  },
  high_ot: {
    label: "High OT",
    dot: "bg-rose-500",
    chipOn: "bg-rose-600 text-white border-rose-600",
    bar: "bg-rose-500",
    text: "text-rose-700",
  },
};

const WINDOW_MARGIN = 24;
const HEADER_HEIGHT = 96;
const DESKTOP_MIN_WIDTH = 380;
const DESKTOP_DEFAULT_WIDTH = 460;
const MOBILE_MIN_WIDTH = 320;
const MOBILE_DEFAULT_WIDTH = 360;
const RESIZE_HANDLE_WIDTH = 10;

function moveMonth(year: number, month: number, delta: number) {
  const next = new Date(year, month - 1 + delta, 1);
  return { year: next.getFullYear(), month: next.getMonth() + 1 };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function clampPercent(value: number) {
  return clamp(value, 0, 100);
}

function mixPercent(value: number, total: number) {
  if (!total) return 0;
  return clampPercent((value / total) * 100);
}

// --- license-aware thresholding ----------------------------------------
//
// Bar & headroom are driven by *this month's* peak week (non-RN) or peak
// biweek (RN), derived from ScheduleEntry. This matches the calendar view:
// if the month is empty, the bar is empty. The HoursLedger snapshot
// (current_cycle_*) is a separate concept — it's shown as context in the
// expanded detail, not in the hero bar, to avoid contradicting the calendar.

function cycleLoad(employee: EmployeeWorkHours) {
  if (employee.license === "RN") {
    return {
      current: employee.peak_biweekly_shifts,
      threshold: RN_BIWEEKLY_OT_SHIFTS,
      cap: RN_HIGH_OT_SHIFTS,
      unit: "shift",
      unitPlural: "shifts",
      cycleLabel: "peak biweek",
    };
  }
  return {
    current: employee.peak_week_hours,
    threshold: WEEKLY_OT_HOURS,
    cap: HIGH_OT_HOURS,
    unit: "h",
    unitPlural: "h",
    cycleLabel: "peak week",
  };
}

function formatLoadValue(value: number, isRN: boolean) {
  return isRN ? `${value}` : `${value.toFixed(1)}h`;
}

function headroomLabel(employee: EmployeeWorkHours) {
  const load = cycleLoad(employee);
  const delta = load.threshold - load.current;
  const isRN = employee.license === "RN";

  if (delta > 0) {
    const value = isRN ? Math.floor(delta) : delta;
    const unit = isRN
      ? `${value === 1 ? load.unit : load.unitPlural} left`
      : "h left";
    return {
      primary: isRN ? `${value} ${unit}` : `${value.toFixed(1)}${unit}`,
      tone: "safe" as const,
    };
  }
  const over = Math.abs(delta);
  if (isRN) {
    return {
      primary: `${Math.ceil(over)} ${over <= 1 ? load.unit : load.unitPlural} over`,
      tone: "over" as const,
    };
  }
  return { primary: `${over.toFixed(1)}h over`, tone: "over" as const };
}

function utilizationPercent(employee: EmployeeWorkHours) {
  const load = cycleLoad(employee);
  return clampPercent((load.current / load.cap) * 100);
}

function thresholdTickPercent(employee: EmployeeWorkHours) {
  const load = cycleLoad(employee);
  return clampPercent((load.threshold / load.cap) * 100);
}

// --- formatters --------------------------------------------------------

function peakLabel(employee: EmployeeWorkHours) {
  if (employee.license === "RN") {
    return `${employee.peak_biweekly_shifts} shifts / peak cycle`;
  }
  return `${employee.peak_week_hours.toFixed(1)}h / peak week`;
}

function projectedOTLabel(employee: EmployeeWorkHours) {
  if (employee.license === "RN") {
    const parts: string[] = [];
    if (employee.projected_overtime_shifts > 0) {
      parts.push(
        `${employee.projected_overtime_shifts} OT shift${employee.projected_overtime_shifts === 1 ? "" : "s"}`,
      );
    }
    if (employee.double_shift_days > 0) {
      parts.push(
        `${employee.double_shift_days} double${employee.double_shift_days === 1 ? "" : "s"}`,
      );
    }
    return parts.length ? parts.join(" · ") : "None projected";
  }
  return employee.projected_overtime_hours > 0
    ? `${employee.projected_overtime_hours.toFixed(1)} OT hours`
    : "None projected";
}

function searchMatch(employee: EmployeeWorkHours, search: string) {
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

// --- summary tiles -----------------------------------------------------

function SummaryTile({
  icon: Icon,
  label,
  primary,
  secondary,
  tone,
}: {
  icon: typeof AlertTriangle;
  label: string;
  primary: string;
  secondary: string;
  tone: "risk" | "ot" | "callout";
}) {
  const tones = {
    risk: "text-amber-700 bg-amber-50 ring-amber-200",
    ot: "text-orange-700 bg-orange-50 ring-orange-200",
    callout: "text-rose-700 bg-rose-50 ring-rose-200",
  } as const;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white/95 p-3 shadow-sm">
      <div className="flex items-center gap-2">
        <div
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-xl ring-1",
            tones[tone],
          )}
        >
          <Icon className="size-3.5" />
        </div>
        <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">
          {label}
        </div>
      </div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-950 tabular-nums">
        {primary}
      </div>
      <div className="mt-0.5 text-xs leading-4 text-slate-500">{secondary}</div>
    </div>
  );
}

// --- employee row ------------------------------------------------------

function EmployeeRow({
  employee,
  expanded,
  onToggle,
}: {
  employee: EmployeeWorkHours;
  expanded: boolean;
  onToggle: () => void;
}) {
  const status = STATUS_META[employee.overtime_status];
  const headroom = headroomLabel(employee);
  const utilPct = utilizationPercent(employee);
  const tickPct = thresholdTickPercent(employee);
  const load = cycleLoad(employee);
  const isRN = employee.license === "RN";
  const currentLabel = formatLoadValue(load.current, isRN);
  const thresholdLabel = formatLoadValue(load.threshold, isRN);

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white transition-colors hover:border-slate-300">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 px-3 py-2.5 text-left"
      >
        <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", status.dot)} />

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="truncate text-sm font-semibold text-slate-950">
              {employee.name}
            </span>
            <span className="shrink-0 text-[11px] font-medium text-slate-500">
              {employee.license}
            </span>
          </div>
          <div className="mt-0.5 truncate text-[11px] text-slate-500">
            {employee.home_unit_id ? `Home ${employee.home_unit_id}` : "Unassigned"}
            {employee.callout_count > 0 ? (
              <span className="ml-1.5 inline-flex items-center gap-0.5 text-rose-600">
                <PhoneOff className="size-3" />
                {employee.callout_count}
              </span>
            ) : null}
          </div>

          {/* Utilization bar */}
          <div className="mt-2 relative h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn("h-full", status.bar)}
              style={{ width: `${utilPct}%` }}
            />
            <div
              className="absolute inset-y-0 w-px bg-slate-400"
              style={{ left: `${tickPct}%` }}
            />
          </div>
          <div className="mt-1 flex items-center justify-between text-[10px] tabular-nums text-slate-400">
            <span>
              {currentLabel} / {thresholdLabel}
            </span>
            <span>{load.cycleLabel}</span>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <div
            className={cn(
              "text-right text-xs font-semibold tabular-nums",
              headroom.tone === "over" ? "text-rose-600" : status.text,
            )}
          >
            {headroom.primary}
          </div>
          <ChevronDown
            className={cn(
              "size-3.5 text-slate-400 transition-transform",
              expanded && "rotate-180",
            )}
          />
        </div>
      </button>

      {expanded ? (
        <div className="border-t border-slate-100 bg-slate-50/60 px-3 py-3 text-xs">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            <DetailItem
              label="This month"
              value={`${employee.scheduled_shifts} shifts · ${employee.scheduled_hours.toFixed(1)}h`}
            />
            <DetailItem label="Peak load" value={peakLabel(employee)} />
            <DetailItem label="Projected OT" value={projectedOTLabel(employee)} />
            <DetailItem
              label="Prior ledger"
              value={`${employee.current_cycle_hours.toFixed(1)}h · ${employee.current_cycle_shifts} shifts`}
            />
          </div>

          {employee.scheduled_shifts > 0 ? (
            <div className="mt-3">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.12em] text-slate-500">
                <span>Home vs float</span>
                <span className="tabular-nums text-slate-700">
                  {employee.home_unit_shifts} / {employee.float_shifts}
                </span>
              </div>
              <div className="mt-1.5 relative h-2 overflow-hidden rounded-full bg-slate-200">
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
            </div>
          ) : null}

          {employee.scheduled_unit_ids.length > 0 ? (
            <div className="mt-3">
              <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">
                Units this month
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {employee.scheduled_unit_ids.map((unit) => (
                  <Badge
                    key={unit}
                    variant="outline"
                    className={cn(
                      "rounded-md px-1.5 py-0 text-[10px] font-medium",
                      unit === employee.primary_unit_id && "border-teal-300 bg-teal-50 text-teal-800",
                    )}
                  >
                    {unit}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}

          {employee.overtime_status !== "healthy" ? (
            <p className={cn("mt-3 text-[11px] leading-5", status.text)}>
              {employee.overtime_detail}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500">
        {label}
      </div>
      <div className="mt-0.5 truncate text-xs font-medium text-slate-900">
        {value}
      </div>
    </div>
  );
}

// --- floating window sizing --------------------------------------------

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

// --- filter chips ------------------------------------------------------

type StatusFilter = "all" | OvertimeStatus;

function StatusChip({
  label,
  count,
  active,
  onClick,
  activeClass,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  activeClass?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
        active
          ? activeClass ?? "bg-slate-900 text-white border-slate-900"
          : "border-slate-200 bg-white text-slate-700 hover:border-slate-300",
      )}
    >
      <span>{label}</span>
      <span
        className={cn(
          "rounded-full px-1.5 py-px text-[10px] tabular-nums",
          active ? "bg-white/20" : "bg-slate-100 text-slate-600",
        )}
      >
        {count}
      </span>
    </button>
  );
}

// --- main --------------------------------------------------------------

export function WorkHoursMonitor() {
  const { open, setOpen, scope, setScope } = useWorkHoursMonitor();
  const initialFrame = getDefaultFrame();
  const [panelWidth, setPanelWidth] = useState(initialFrame.width);
  const [panelHeight, setPanelHeight] = useState(initialFrame.height);
  const [{ x, y }, setPosition] = useState({ x: initialFrame.x, y: initialFrame.y });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [licenseFilter, setLicenseFilter] = useState<"all" | LicenseType>("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const dragState = useRef<
    | { kind: "move"; offsetX: number; offsetY: number; pointerId: number }
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

  const employees = data?.employees ?? [];
  const summary = data?.summary;

  // Counts for status chips — respect search + license, not status (self-count).
  const statusCounts = useMemo(() => {
    const counts = { all: 0, healthy: 0, near_ot: 0, overtime: 0, high_ot: 0 };
    for (const e of employees) {
      if (!searchMatch(e, deferredSearch)) continue;
      if (licenseFilter !== "all" && e.license !== licenseFilter) continue;
      counts.all += 1;
      counts[e.overtime_status] += 1;
    }
    return counts;
  }, [employees, deferredSearch, licenseFilter]);

  const licenseCounts = useMemo(() => {
    const counts: Record<string, number> = { all: 0, RN: 0, LPN: 0, CNA: 0, PCT: 0 };
    for (const e of employees) {
      if (!searchMatch(e, deferredSearch)) continue;
      counts.all += 1;
      counts[e.license] = (counts[e.license] ?? 0) + 1;
    }
    return counts;
  }, [employees, deferredSearch]);

  const filtered = useMemo(() => {
    return employees.filter((e) => {
      if (!searchMatch(e, deferredSearch)) return false;
      if (licenseFilter !== "all" && e.license !== licenseFilter) return false;
      if (statusFilter !== "all" && e.overtime_status !== statusFilter) return false;
      return true;
    });
  }, [employees, deferredSearch, licenseFilter, statusFilter]);

  const atRiskTotal = summary
    ? summary.employees_near_ot + summary.employees_in_ot + summary.employees_high_ot
    : 0;
  const projectedOT = useMemo(() => {
    let hours = 0;
    let shifts = 0;
    for (const e of employees) {
      hours += e.projected_overtime_hours;
      shifts += e.projected_overtime_shifts;
    }
    return { hours, shifts };
  }, [employees]);
  const repeatCallouts = useMemo(
    () => employees.filter((e) => e.callout_count > 1).length,
    [employees],
  );

  function toggleExpanded(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

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
      if (event.key === "Escape") setOpen(false);
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

  const statusFilters: { key: StatusFilter; label: string; count: number; activeClass?: string }[] = [
    { key: "all", label: "All", count: statusCounts.all },
    {
      key: "near_ot",
      label: "Watch",
      count: statusCounts.near_ot,
      activeClass: STATUS_META.near_ot.chipOn,
    },
    {
      key: "overtime",
      label: "OT",
      count: statusCounts.overtime,
      activeClass: STATUS_META.overtime.chipOn,
    },
    {
      key: "high_ot",
      label: "High",
      count: statusCounts.high_ot,
      activeClass: STATUS_META.high_ot.chipOn,
    },
    {
      key: "healthy",
      label: "Healthy",
      count: statusCounts.healthy,
      activeClass: STATUS_META.healthy.chipOn,
    },
  ];

  const licenseFilters: { key: "all" | LicenseType; label: string }[] = [
    { key: "all", label: "All roles" },
    { key: "RN", label: "RN" },
    { key: "LPN", label: "LPN" },
    { key: "CNA", label: "CNA" },
    { key: "PCT", label: "PCT" },
  ];

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
          className="fixed z-50 overflow-hidden rounded-[22px] border border-slate-200 bg-white shadow-2xl shadow-slate-900/15"
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

          {/* Header */}
          <div
            className="flex cursor-grab items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 active:cursor-grabbing"
            onPointerDown={handleMoveStart}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerEnd}
            onPointerCancel={handlePointerEnd}
          >
            <div className="min-w-0">
              <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">
                Workload Monitor
              </div>
              <div className="mt-0.5 text-base font-semibold tracking-tight text-slate-950">
                {MONTH_NAMES[scope.month - 1]} {scope.year}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => {
                  event.stopPropagation();
                  setScope((current) => moveMonth(current.year, current.month, -1));
                }}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <ArrowLeft className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => {
                  event.stopPropagation();
                  setScope((current) => moveMonth(current.year, current.month, 1));
                }}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <ArrowRight className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(event) => {
                  event.stopPropagation();
                  setOpen(false);
                }}
                onPointerDown={(event) => event.stopPropagation()}
              >
                <X className="size-4" />
              </Button>
            </div>
          </div>

          {/* Body */}
          <div
            className="overflow-y-auto bg-slate-50/60"
            style={{ height: `${panelHeight - HEADER_HEIGHT}px` }}
          >
            <div className="space-y-3 px-3 py-3">
              {/* Summary strip */}
              <div className="grid grid-cols-3 gap-2">
                <SummaryTile
                  icon={AlertTriangle}
                  label="At risk"
                  primary={`${atRiskTotal}`}
                  secondary={
                    summary
                      ? `${summary.employees_near_ot} watch · ${summary.employees_in_ot} OT · ${summary.employees_high_ot} high`
                      : "—"
                  }
                  tone="risk"
                />
                <SummaryTile
                  icon={TrendingUp}
                  label="Projected OT"
                  primary={
                    projectedOT.hours > 0
                      ? `${projectedOT.hours.toFixed(1)}h`
                      : projectedOT.shifts > 0
                        ? `${projectedOT.shifts}`
                        : "0"
                  }
                  secondary={
                    projectedOT.shifts > 0
                      ? `${projectedOT.shifts} RN shift${projectedOT.shifts === 1 ? "" : "s"}`
                      : "This month"
                  }
                  tone="ot"
                />
                <SummaryTile
                  icon={PhoneOff}
                  label="Repeat callouts"
                  primary={`${repeatCallouts}`}
                  secondary="Staff > 1 callout"
                  tone="callout"
                />
              </div>

              {/* Filters */}
              <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-2.5 shadow-sm">
                <label className="relative block">
                  <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-slate-400" />
                  <Input
                    className="h-9 rounded-lg bg-white pl-8 text-sm"
                    placeholder="Search name, ID, unit..."
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {statusFilters.map((f) => (
                    <StatusChip
                      key={f.key}
                      label={f.label}
                      count={f.count}
                      active={statusFilter === f.key}
                      activeClass={f.activeClass}
                      onClick={() => setStatusFilter(f.key)}
                    />
                  ))}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {licenseFilters.map((f) => (
                    <StatusChip
                      key={f.key}
                      label={f.label}
                      count={licenseCounts[f.key] ?? 0}
                      active={licenseFilter === f.key}
                      onClick={() => setLicenseFilter(f.key)}
                    />
                  ))}
                </div>
              </div>

              {/* List */}
              {isLoading ? (
                <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
                  Loading workload snapshot...
                </div>
              ) : isError ? (
                <div className="rounded-xl border border-destructive/30 bg-red-50 p-6 text-center text-sm text-destructive">
                  {error.message}
                </div>
              ) : filtered.length === 0 ? (
                <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
                  No employees match the current filters.
                </div>
              ) : (
                <div className="space-y-1.5">
                  {filtered.map((employee) => (
                    <EmployeeRow
                      key={employee.employee_id}
                      employee={employee}
                      expanded={expanded.has(employee.employee_id)}
                      onToggle={() => toggleExpanded(employee.employee_id)}
                    />
                  ))}
                </div>
              )}

              <div className="py-1 text-center text-[10px] text-slate-400">
                {filtered.length} of {employees.length} staff shown · thresholds by license
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
