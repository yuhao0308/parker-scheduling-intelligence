"use client";

import { type ReactNode, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Gauge,
  HeartPulse,
  Search,
  ShieldCheck,
  TrendingUp,
  Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useMonthlySchedule, useUnits, useWorkHoursSnapshot } from "@/lib/queries";
import type {
  EmployeeWorkHours,
  LicenseType,
  MonthlySchedule,
  ShiftSlot,
  WorkloadPeriod,
} from "@/lib/types";
import { cn } from "@/lib/utils";

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

const WEEKLY_OT_THRESHOLD = 37.5;
const SHIFT_DURATION_HOURS = 8.25;
const RN_BIWEEKLY_SHIFT_LIMIT = 10;
const RN_BIWEEKLY_HOUR_LIMIT = 82.5;

type RuleView = "weekly" | "rn" | "month";
type RoleFilter = "all" | LicenseType;
type PeriodOption = { value: string; label: string };
type PeriodRange = { start: string; end: string; label: string };
type CoverageTone = "safe" | "warning" | "danger" | "neutral";
type CardTone = "neutral" | "warning" | "danger" | "capacity";
type ConfirmationStats = {
  accepted: number;
  acceptedPct: number;
  actionNeeded: number;
  declined: number;
  pending: number;
  phase: string;
  replaced: number;
  total: number;
  unsent: number;
};
type RunwayStats = {
  close: number;
  noRoom: number;
  oneShift: number;
  over: number;
  safe: number;
  total: number;
  twoShifts: number;
};
type ExceptionRow = {
  employee: EmployeeWorkHours;
  note: string;
  runway: number;
  status: EmployeeWorkHours["overtime_status"];
};
type NextRiskRow = {
  employee: EmployeeWorkHours;
  runway: number;
  status: EmployeeWorkHours["overtime_status"];
};

const ROLE_OPTIONS: { value: RoleFilter; label: string }[] = [
  { value: "all", label: "All roles" },
  { value: "RN", label: "RN" },
  { value: "LPN", label: "LPN" },
  { value: "CNA", label: "CNA" },
  { value: "PCT", label: "PCT" },
];

const STATUS_META = {
  healthy: {
    label: "Safe",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-800",
    text: "text-emerald-700",
  },
  near_ot: {
    label: "Approaching",
    badge: "border-amber-200 bg-amber-50 text-amber-800",
    text: "text-amber-700",
  },
  overtime: {
    label: "OT risk",
    badge: "border-orange-200 bg-orange-50 text-orange-800",
    text: "text-orange-700",
  },
  high_ot: {
    label: "Over",
    badge: "border-rose-200 bg-rose-50 text-rose-800",
    text: "text-rose-700",
  },
} satisfies Record<
  EmployeeWorkHours["overtime_status"],
  { label: string; badge: string; text: string }
>;

function addMonths(year: number, month: number, delta: number) {
  const next = new Date(year, month - 1 + delta, 1);
  return { year: next.getFullYear(), month: next.getMonth() + 1 };
}

function formatHours(value: number | undefined | null) {
  return `${(value ?? 0).toFixed(1)}h`;
}

function percent(value: number, total: number) {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(100, (value / total) * 100));
}

function riskRankForStatus(status: EmployeeWorkHours["overtime_status"]) {
  return (
    { high_ot: 0, overtime: 1, near_ot: 2, healthy: 3 }[status] ?? 4
  );
}

function shortDate(value?: string | null) {
  if (!value) return "";
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return "";
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function cycleRangeLabel(employee: EmployeeWorkHours) {
  const start = shortDate(employee.cycle_start_date);
  const end = shortDate(employee.cycle_end_date);
  return start && end ? `${start}-${end}` : "Current cycle";
}

function periodRangeLabel(period: WorkloadPeriod) {
  const start = shortDate(period.start_date);
  const end = shortDate(period.end_date);
  return start && end ? `${start}-${end}` : "Rule period";
}

function periodKey(period: WorkloadPeriod) {
  return `${period.start_date}|${period.end_date}`;
}

function isoDate(year: number, month: number, day: number) {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function monthEndDate(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

function localTodayIso() {
  const today = new Date();
  return isoDate(today.getFullYear(), today.getMonth() + 1, today.getDate());
}

function parseIsoDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month ?? 1) - 1, day ?? 1);
}

function daysBetween(start: string, end: string) {
  const startDate = parseIsoDate(start);
  const endDate = parseIsoDate(end);
  const msPerDay = 24 * 60 * 60 * 1000;
  return Math.round((endDate.getTime() - startDate.getTime()) / msPerDay);
}

function periodRangeFromKey(
  activePeriodKey: string,
  year: number,
  month: number,
  label: string,
): PeriodRange {
  if (activePeriodKey.includes("|")) {
    const [start, end] = activePeriodKey.split("|");
    if (start && end) return { start, end, label };
  }

  return {
    start: isoDate(year, month, 1),
    end: isoDate(year, month, monthEndDate(year, month)),
    label,
  };
}

function periodPhase(range: PeriodRange) {
  const today = localTodayIso();
  if (today < range.start) {
    const days = Math.max(0, daysBetween(today, range.start));
    return days === 0 ? "Starts today" : `Starts in ${days}d`;
  }
  if (today > range.end) return "Completed period";
  return "Live period";
}

function unitMatches(employee: EmployeeWorkHours, unitId: string) {
  return (
    employee.home_unit_id === unitId ||
    employee.primary_unit_id === unitId ||
    employee.scheduled_unit_ids.includes(unitId)
  );
}

function searchMatches(employee: EmployeeWorkHours, query: string) {
  if (!query.trim()) return true;
  const haystack = [
    employee.name,
    employee.employee_id,
    employee.license,
    employee.home_unit_id ?? "",
    employee.primary_unit_id ?? "",
    employee.scheduled_unit_ids.join(" "),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.trim().toLowerCase());
}

function fallbackWeeklyPeriod(employee: EmployeeWorkHours): WorkloadPeriod {
  const projected = employee.peak_week_hours ?? 0;
  return {
    period_type: "week",
    start_date: "",
    end_date: "",
    worked_hours: 0,
    worked_shifts: 0,
    scheduled_hours: projected,
    scheduled_shifts: 0,
    projected_hours: projected,
    projected_shifts: 0,
    threshold_hours: WEEKLY_OT_THRESHOLD,
    remaining_hours: Math.max(0, WEEKLY_OT_THRESHOLD - projected),
    overtime_hours: Math.max(0, projected - WEEKLY_OT_THRESHOLD),
    double_shift_days: 0,
  };
}

function fallbackRnPeriod(employee: EmployeeWorkHours): WorkloadPeriod {
  const worked = employee.worked_hours_this_cycle ?? 0;
  const scheduled = employee.scheduled_hours_this_cycle ?? 0;
  const projected = worked + scheduled;
  const threshold = RN_BIWEEKLY_HOUR_LIMIT;
  return {
    period_type: "biweekly",
    start_date: employee.cycle_start_date ?? "",
    end_date: employee.cycle_end_date ?? "",
    worked_hours: worked,
    worked_shifts: employee.current_cycle_shifts ?? 0,
    scheduled_hours: scheduled,
    scheduled_shifts: 0,
    projected_hours: projected,
    projected_shifts: employee.peak_biweekly_shifts ?? 0,
    threshold_hours: threshold,
    remaining_hours: Math.max(0, threshold - projected),
    overtime_hours: Math.max(0, projected - threshold),
    double_shift_days: employee.double_shift_days ?? 0,
  };
}

function weeklyPeriods(employee: EmployeeWorkHours) {
  return employee.weekly_periods?.length
    ? employee.weekly_periods
    : [fallbackWeeklyPeriod(employee)];
}

function rnPeriods(employee: EmployeeWorkHours) {
  return employee.biweekly_periods?.length
    ? employee.biweekly_periods
    : [fallbackRnPeriod(employee)];
}

function periodStats(period: WorkloadPeriod) {
  const threshold = period.threshold_hours || WEEKLY_OT_THRESHOLD;
  const worked = period.worked_hours ?? 0;
  const scheduled = period.scheduled_hours ?? 0;
  const projected = period.projected_hours ?? worked + scheduled;
  const over = Math.max(0, period.overtime_hours ?? projected - threshold);
  const remaining = Math.max(0, period.remaining_hours ?? threshold - projected);
  const trackMax = Math.max(threshold + over, projected, 1);
  const workedInLimit = Math.min(worked, threshold);
  const scheduledInLimit = Math.min(
    scheduled,
    Math.max(0, threshold - workedInLimit),
  );

  return {
    worked,
    scheduled,
    threshold,
    projected,
    over,
    remaining,
    workedPct: percent(workedInLimit, trackMax),
    scheduledPct: percent(scheduledInLimit, trackMax),
    remainingPct: percent(remaining, trackMax),
    overPct: percent(over, trackMax),
    thresholdPct: percent(threshold, trackMax),
  };
}

function worstPeriod(periods: WorkloadPeriod[]) {
  return [...periods].sort((a, b) => {
    const aStats = periodStats(a);
    const bStats = periodStats(b);
    const overDiff = bStats.over - aStats.over;
    if (overDiff !== 0) return overDiff;
    return bStats.projected - aStats.projected;
  })[0];
}

function periodsForView(employee: EmployeeWorkHours, view: RuleView) {
  if (view === "weekly") return weeklyPeriods(employee);
  if (view === "rn") return rnPeriods(employee);
  return [];
}

function selectedPeriodForEmployee(
  employee: EmployeeWorkHours,
  view: RuleView,
  selectedPeriodKey: string,
) {
  const periods = periodsForView(employee, view);
  if (periods.length === 0) return null;
  return (
    periods.find((period) => periodKey(period) === selectedPeriodKey) ??
    periods[0]
  );
}

function periodStatus(period: WorkloadPeriod | null, view: RuleView) {
  if (!period) return "healthy" as EmployeeWorkHours["overtime_status"];
  const stats = periodStats(period);

  if (view === "rn") {
    if (
      period.projected_shifts > RN_BIWEEKLY_SHIFT_LIMIT ||
      period.double_shift_days > 1
    ) {
      return "high_ot" as const;
    }
    if (period.double_shift_days > 0 || stats.over > 0) {
      return "overtime" as const;
    }
    if (
      stats.remaining <= 8.25 ||
      RN_BIWEEKLY_SHIFT_LIMIT - period.projected_shifts <= 1
    ) {
      return "near_ot" as const;
    }
    return "healthy" as const;
  }

  if (stats.projected > WEEKLY_OT_THRESHOLD + 25) return "high_ot" as const;
  if (stats.over > 0) return "overtime" as const;
  if (stats.remaining <= 8.25) return "near_ot" as const;
  return "healthy" as const;
}

function employeeStatus(
  employee: EmployeeWorkHours,
  view: RuleView,
  selectedPeriodKey: string,
) {
  if (view === "month") return employee.overtime_status;
  return periodStatus(
    selectedPeriodForEmployee(employee, view, selectedPeriodKey),
    view,
  );
}

function selectedStats(
  employee: EmployeeWorkHours,
  view: RuleView,
  selectedPeriodKey: string,
) {
  const period = selectedPeriodForEmployee(employee, view, selectedPeriodKey);
  return period ? periodStats(period) : null;
}

function shiftRunway(
  employee: EmployeeWorkHours,
  view: RuleView,
  selectedPeriodKey: string,
) {
  const status = employeeStatus(employee, view, selectedPeriodKey);
  if (status === "overtime" || status === "high_ot") return 0;

  const stats = selectedStats(employee, view, selectedPeriodKey);
  if (!stats) {
    const budget = employee.budget_hours_this_cycle ?? 80;
    return Math.max(0, (budget - employee.scheduled_hours) / SHIFT_DURATION_HOURS);
  }

  const hoursRoom = stats.remaining / SHIFT_DURATION_HOURS;
  if (view !== "rn") return Math.max(0, hoursRoom);

  const period = selectedPeriodForEmployee(employee, "rn", selectedPeriodKey);
  const shiftRoom = period
    ? RN_BIWEEKLY_SHIFT_LIMIT - period.projected_shifts
    : hoursRoom;
  return Math.max(0, Math.min(hoursRoom, shiftRoom));
}

function slotsForRange(
  schedule: MonthlySchedule | undefined,
  range: PeriodRange,
  unitId: string,
) {
  return (
    schedule?.days.flatMap((day) =>
      day.slots.filter(
        (slot) =>
          slot.shift_date >= range.start &&
          slot.shift_date <= range.end &&
          (unitId === "all" || slot.unit_id === unitId),
      ),
    ) ?? []
  );
}

function confirmedAssignments(slot: ShiftSlot) {
  return slot.assigned_employees.filter(
    (employee) => employee.confirmation_status === "ACCEPTED",
  ).length;
}

function noteFor(
  employee: EmployeeWorkHours,
  view: RuleView,
  selectedPeriodKey: string,
) {
  if (view === "month") {
    return employee.overtime_detail || "Use a rule-period view for OT details";
  }

  if (view === "rn" || employee.license === "RN") {
    const period =
      selectedPeriodForEmployee(employee, "rn", selectedPeriodKey) ??
      worstPeriod(rnPeriods(employee));
    const cycle = periodStats(period);
    const doubleDays = period.double_shift_days ?? employee.double_shift_days ?? 0;
    const periodLabel = periodRangeLabel(period) || cycleRangeLabel(employee);
    if (doubleDays > 0 && cycle.over > 0) {
      return `${doubleDays} double-shift day${doubleDays === 1 ? "" : "s"} and ${formatHours(cycle.over)} over ${periodLabel}`;
    }
    if (doubleDays > 0) {
      return `${doubleDays} double-shift day${doubleDays === 1 ? "" : "s"} projected`;
    }
    if (cycle.over > 0) return `${formatHours(cycle.over)} over ${periodLabel}`;
    if (cycle.remaining <= 8.25) return "Within one shift of RN biweekly limit";
    return "Cycle capacity available";
  }

  const period =
    selectedPeriodForEmployee(employee, "weekly", selectedPeriodKey) ??
    worstPeriod(weeklyPeriods(employee));
  const weekly = periodStats(period);
  if (weekly.over > 0) {
    return `${formatHours(weekly.over)} over ${periodRangeLabel(period)}`;
  }
  if (weekly.remaining <= 8.25) return "Within one shift of weekly OT";
  return "Weekly capacity available";
}

function viewIncludes(employee: EmployeeWorkHours, view: RuleView) {
  if (view === "weekly") return employee.license !== "RN";
  if (view === "rn") return employee.license === "RN";
  return true;
}

export default function WorkloadPage() {
  const [year, setYear] = useState(2026);
  const [month, setMonth] = useState(4);
  const [view, setView] = useState<RuleView>("weekly");
  const [unitId, setUnitId] = useState("all");
  const [role, setRole] = useState<RoleFilter>("all");
  const [periodFilter, setPeriodFilter] = useState("default");
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, error } = useWorkHoursSnapshot(year, month);
  const { data: units } = useUnits();
  const { data: scheduleData, isLoading: isScheduleLoading } =
    useMonthlySchedule(year, month);

  const periodOptions = useMemo(() => {
    if (view === "month") {
      return [{ value: "month", label: `${MONTH_NAMES[month - 1]} ${year}` }];
    }

    const options = new Map<string, PeriodOption>();
    for (const employee of data?.employees ?? []) {
      if (!viewIncludes(employee, view)) continue;
      for (const period of periodsForView(employee, view)) {
        options.set(periodKey(period), {
          value: periodKey(period),
          label: periodRangeLabel(period),
        });
      }
    }

    return [...options.values()];
  }, [data?.employees, month, view, year]);

  const activePeriodKey = periodOptions.some(
    (option) => option.value === periodFilter,
  )
    ? periodFilter
    : (periodOptions[0]?.value ?? (view === "month" ? "month" : "none"));

  const employees = useMemo(() => {
    const rows = data?.employees ?? [];
    return rows
      .filter((employee) => viewIncludes(employee, view))
      .filter((employee) => role === "all" || employee.license === role)
      .filter((employee) => unitId === "all" || unitMatches(employee, unitId))
      .filter((employee) => searchMatches(employee, search))
      .sort((a, b) => {
        const risk =
          riskRankForStatus(employeeStatus(a, view, activePeriodKey)) -
          riskRankForStatus(employeeStatus(b, view, activePeriodKey));
        if (risk !== 0) return risk;
        if (view === "rn") {
          return (
            (selectedStats(b, view, activePeriodKey)?.projected ?? 0) -
            (selectedStats(a, view, activePeriodKey)?.projected ?? 0)
          );
        }
        if (view === "weekly") {
          return (
            (selectedStats(b, view, activePeriodKey)?.projected ?? 0) -
            (selectedStats(a, view, activePeriodKey)?.projected ?? 0)
          );
        }
        return b.scheduled_hours - a.scheduled_hours;
      });
  }, [activePeriodKey, data?.employees, role, search, unitId, view]);

  const activePeriodLabel =
    periodOptions.find((option) => option.value === activePeriodKey)?.label ??
    `${MONTH_NAMES[month - 1]} ${year}`;

  const activeRange = useMemo(
    () => periodRangeFromKey(activePeriodKey, year, month, activePeriodLabel),
    [activePeriodKey, activePeriodLabel, month, year],
  );

  const scopedSlots = useMemo(
    () => slotsForRange(scheduleData, activeRange, unitId),
    [activeRange, scheduleData, unitId],
  );

  const coverageStats = useMemo(() => {
    const required = scopedSlots.reduce(
      (sum, slot) => sum + slot.required_count,
      0,
    );
    const assigned = scopedSlots.reduce(
      (sum, slot) => sum + slot.assigned_employees.length,
      0,
    );
    const confirmed = scopedSlots.reduce(
      (sum, slot) => sum + confirmedAssignments(slot),
      0,
    );
    const openAssignments = scopedSlots.reduce(
      (sum, slot) =>
        sum + Math.max(0, slot.required_count - slot.assigned_employees.length),
      0,
    );
    const gapSlots = scopedSlots.filter(
      (slot) =>
        slot.required_count > 0 &&
        slot.assigned_employees.length < slot.required_count,
    ).length;
    const unresolvedCallouts = scopedSlots.reduce(
      (sum, slot) => sum + slot.unresolved_callout_count,
      0,
    );
    const toneRank: Record<CoverageTone, number> = {
      neutral: 0,
      safe: 1,
      warning: 2,
      danger: 3,
    };
    const dayMap = new Map<string, CoverageTone>();
    for (const slot of scopedSlots) {
      let tone: CoverageTone = "safe";
      if (slot.required_count <= 0) {
        tone = "neutral";
      } else if (
        slot.unresolved_callout_count > 0 ||
        slot.assigned_employees.length === 0
      ) {
        tone = "danger";
      } else if (slot.assigned_employees.length < slot.required_count) {
        tone = "warning";
      }
      const current = dayMap.get(slot.shift_date) ?? "neutral";
      if (toneRank[tone] > toneRank[current]) {
        dayMap.set(slot.shift_date, tone);
      }
    }

    return {
      assigned,
      confirmed,
      daySignals: [...dayMap.entries()].map(([date, tone]) => ({ date, tone })),
      gapSlots,
      openAssignments,
      plannedPct: Math.round(percent(required - openAssignments, required)),
      required,
      slotCount: scopedSlots.length,
      unresolvedCallouts,
    };
  }, [scopedSlots]);

  const confirmationStats = useMemo(() => {
    const counts = {
      accepted: 0,
      declined: 0,
      pending: 0,
      replaced: 0,
      unsent: 0,
    };
    for (const slot of scopedSlots) {
      for (const employee of slot.assigned_employees) {
        if (role !== "all" && employee.license !== role) continue;
        const status = employee.confirmation_status ?? "UNSENT";
        if (status === "ACCEPTED") counts.accepted += 1;
        else if (status === "DECLINED") counts.declined += 1;
        else if (status === "PENDING") counts.pending += 1;
        else if (status === "REPLACED") counts.replaced += 1;
        else counts.unsent += 1;
      }
    }
    const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
    return {
      ...counts,
      actionNeeded:
        counts.declined + counts.pending + counts.replaced + counts.unsent,
      acceptedPct: Math.round(percent(counts.accepted, total)),
      phase: periodPhase(activeRange),
      total,
    };
  }, [activeRange, role, scopedSlots]);

  const runwayStats = useMemo(() => {
    const buckets = {
      noRoom: 0,
      oneShift: 0,
      over: 0,
      safe: 0,
      twoShifts: 0,
    };
    for (const employee of employees) {
      const status = employeeStatus(employee, view, activePeriodKey);
      const runway = shiftRunway(employee, view, activePeriodKey);
      if (status === "overtime" || status === "high_ot") {
        buckets.over += 1;
      } else if (runway <= 0.5) {
        buckets.noRoom += 1;
      } else if (runway <= 1) {
        buckets.oneShift += 1;
      } else if (runway <= 2) {
        buckets.twoShifts += 1;
      } else {
        buckets.safe += 1;
      }
    }
    return {
      ...buckets,
      close: buckets.noRoom + buckets.oneShift,
      total: employees.length,
    };
  }, [activePeriodKey, employees, view]);

  const exceptionStats = useMemo(() => {
    const rows = employees
      .map((employee) => {
        const status = employeeStatus(employee, view, activePeriodKey);
        return {
          employee,
          note: noteFor(employee, view, activePeriodKey),
          runway: shiftRunway(employee, view, activePeriodKey),
          status,
        };
      })
      .filter(
        (item) => item.status === "overtime" || item.status === "high_ot",
      )
      .sort((a, b) => {
        const risk =
          riskRankForStatus(a.status) - riskRankForStatus(b.status);
        if (risk !== 0) return risk;
        return a.runway - b.runway;
      });

    const nextRisk = employees
      .map((employee) => ({
        employee,
        runway: shiftRunway(employee, view, activePeriodKey),
        status: employeeStatus(employee, view, activePeriodKey),
      }))
      .filter(
        (item) => item.status !== "overtime" && item.status !== "high_ot",
      )
      .sort((a, b) => a.runway - b.runway)[0];

    return {
      high: rows.filter((item) => item.status === "high_ot").length,
      nextRisk,
      rows,
    };
  }, [activePeriodKey, employees, view]);

  const capacityStats = useMemo(() => {
    const byRole: Record<LicenseType, number> = {
      CNA: 0,
      LPN: 0,
      PCT: 0,
      RN: 0,
    };
    let total = 0;
    for (const employee of employees) {
      const status = employeeStatus(employee, view, activePeriodKey);
      if (status === "overtime" || status === "high_ot") continue;
      const shifts = Math.floor(shiftRunway(employee, view, activePeriodKey));
      if (shifts <= 0) continue;
      byRole[employee.license] += shifts;
      total += shifts;
    }
    const topRole = (Object.entries(byRole) as [LicenseType, number][])
      .filter(([, shifts]) => shifts > 0)
      .sort((a, b) => b[1] - a[1])[0];

    return { byRole, topRole, total };
  }, [activePeriodKey, employees, view]);

  const riskMix = useMemo(() => {
    const counts = { healthy: 0, near_ot: 0, overtime: 0, high_ot: 0 };
    for (const employee of employees) {
      counts[employeeStatus(employee, view, activePeriodKey)] += 1;
    }
    return counts;
  }, [activePeriodKey, employees, view]);

  const rolePressure = useMemo(() => {
    const roles: LicenseType[] = ["RN", "LPN", "CNA", "PCT"];
    return roles
      .map((license) => {
        const rows = employees.filter((employee) => employee.license === license);
        const risky = rows.filter((employee) => {
          const status = employeeStatus(employee, view, activePeriodKey);
          return status !== "healthy";
        }).length;
        return {
          license,
          count: rows.length,
          risky,
          scheduled: rows.reduce((sum, employee) => {
            const stats = selectedStats(employee, view, activePeriodKey);
            return sum + (stats ? stats.scheduled : employee.scheduled_hours);
          }, 0),
        };
      })
      .filter((item) => item.count > 0);
  }, [activePeriodKey, employees, view]);

  function moveMonth(delta: number) {
    const next = addMonths(year, month, delta);
    setYear(next.year);
    setMonth(next.month);
  }

  function goToToday() {
    const today = new Date();
    setYear(today.getFullYear());
    setMonth(today.getMonth() + 1);
  }

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <header className="flex flex-col gap-4 border-b border-slate-200 pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
            <HeartPulse className="size-4 text-rose-500" />
            Healthcare staffing analytics
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            Workload Monitor
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Tracks worked hours, scheduled hours, remaining capacity, and
            overtime exposure using the rule period that applies to each role.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={goToToday}>
            Today
          </Button>
          <Button variant="outline" size="icon-sm" onClick={() => moveMonth(-1)}>
            <ArrowLeft className="size-4" />
          </Button>
          <div className="flex min-w-40 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-900">
            <CalendarDays className="size-4 text-slate-500" />
            {MONTH_NAMES[month - 1]} {year}
          </div>
          <Button variant="outline" size="icon-sm" onClick={() => moveMonth(1)}>
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </header>

      <section className="grid gap-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm lg:grid-cols-[1.1fr_0.8fr_0.7fr_0.9fr_0.9fr]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="h-10 pl-9"
            placeholder="Search employee, ID, or unit"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

        <select
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={unitId}
          onChange={(event) => setUnitId(event.target.value)}
        >
          <option value="all">All units</option>
          {units?.map((unit) => (
            <option key={unit.unit_id} value={unit.unit_id}>
              {unit.unit_id} - {unit.name}
            </option>
          ))}
        </select>

        <select
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={role}
          onChange={(event) => setRole(event.target.value as RoleFilter)}
        >
          {ROLE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <select
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900"
          value={view}
          onChange={(event) => setView(event.target.value as RuleView)}
        >
          <option value="weekly">Weekly OT - CNA/PCT/LPN</option>
          <option value="rn">RN OT - daily and biweekly</option>
          <option value="month">Month balance - all roles</option>
        </select>

        <select
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 disabled:bg-slate-50 disabled:text-slate-500"
          value={activePeriodKey}
          onChange={(event) => setPeriodFilter(event.target.value)}
          disabled={view === "month" || periodOptions.length === 0}
        >
          {periodOptions.length === 0 ? (
            <option value="none">No periods</option>
          ) : (
            periodOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {view === "weekly"
                  ? `Week ${option.label}`
                  : view === "rn"
                    ? `Biweekly ${option.label}`
                    : option.label}
              </option>
            ))
          )}
        </select>
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <InsightCard
          icon={Users}
          label="Coverage health"
          value={isScheduleLoading ? "..." : coverageStats.openAssignments}
          detail={
            isScheduleLoading
              ? "Reading schedule coverage"
              : coverageStats.slotCount === 0
                ? "No coverage slots in period"
                : `${coverageStats.gapSlots} thin slots - ${coverageStats.plannedPct}% total plan`
          }
          tone={
            coverageStats.openAssignments > 0 || coverageStats.unresolvedCallouts > 0
              ? "danger"
              : coverageStats.gapSlots > 0
                ? "warning"
                : "capacity"
          }
        >
          <CoverageSignalStrip
            loading={isScheduleLoading}
            signals={coverageStats.daySignals}
          />
        </InsightCard>

        <InsightCard
          icon={ShieldCheck}
          label="Plan confidence"
          value={
            isScheduleLoading
              ? "..."
              : confirmationStats.total > 0
                ? `${confirmationStats.acceptedPct}%`
                : "No plan"
          }
          detail={
            confirmationStats.total > 0
              ? `${confirmationStats.phase} - ${confirmationStats.accepted}/${confirmationStats.total} accepted`
              : confirmationStats.phase
          }
          tone={
            confirmationStats.declined > 0
              ? "danger"
              : confirmationStats.acceptedPct < 70 && confirmationStats.total > 0
                ? "warning"
                : "neutral"
          }
        >
          <ConfirmationStack stats={confirmationStats} />
        </InsightCard>

        <InsightCard
          icon={Gauge}
          label="OT runway"
          value={runwayStats.close}
          detail={`${runwayStats.over} over - ${runwayStats.safe} with 2+ shifts`}
          tone={runwayStats.over > 0 ? "danger" : runwayStats.close > 0 ? "warning" : "capacity"}
        >
          <RunwayStack stats={runwayStats} />
        </InsightCard>

        <InsightCard
          icon={AlertTriangle}
          label="Active exceptions"
          value={exceptionStats.rows.length}
          detail={
            exceptionStats.rows.length > 0
              ? `${exceptionStats.high} high-risk staff`
              : exceptionStats.nextRisk
                ? `Next: ${exceptionStats.nextRisk.employee.name}`
                : "No active exceptions"
          }
          tone={exceptionStats.rows.length > 0 ? "danger" : "capacity"}
        >
          <ExceptionPreview
            nextRisk={exceptionStats.nextRisk}
            rows={exceptionStats.rows}
          />
        </InsightCard>

        <InsightCard
          icon={TrendingUp}
          label="Usable capacity"
          value={capacityStats.total}
          detail={
            capacityStats.topRole
              ? `${capacityStats.topRole[0]} has ${capacityStats.topRole[1]} whole shifts`
              : "No whole-shift room in view"
          }
          tone={capacityStats.total > 0 ? "capacity" : "warning"}
        >
          <CapacityByRole byRole={capacityStats.byRole} total={capacityStats.total} />
        </InsightCard>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.8fr)_minmax(320px,0.9fr)]">
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-3 border-b border-slate-100 px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">
                Employee Workload Bars
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                {view === "weekly"
                  ? `Showing all CNA, PCT, and LPN employees for ${activePeriodLabel}.`
                  : view === "rn"
                    ? `Showing all RN employees for ${activePeriodLabel}, including daily double-shift risk.`
                    : "Month balance shows scheduled and actual workload without pretending the month is an OT period."}
              </p>
              {view !== "month" ? <WorkloadLegend /> : null}
            </div>
            <ViewTabs view={view} onChange={setView} />
          </div>

          <div className="divide-y divide-slate-100">
            {isLoading ? (
              <EmptyState label="Loading workload snapshot..." />
            ) : isError ? (
              <EmptyState label={error.message} tone="danger" />
            ) : employees.length === 0 ? (
              <EmptyState label="No employees match the current filters." />
            ) : (
              employees.map((employee) => (
                <RiskRow
                  key={employee.employee_id}
                  employee={employee}
                  view={view}
                  selectedPeriodKey={activePeriodKey}
                />
              ))
            )}
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-950">Risk mix</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Staff in the current rule view
                </p>
              </div>
              <Badge variant="outline" className="rounded-md">
                {employees.length} staff
              </Badge>
            </div>
            <RiskMixBar counts={riskMix} />
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <RiskCount label="Safe" value={riskMix.healthy} tone="safe" />
              <RiskCount label="Approaching" value={riskMix.near_ot} tone="warning" />
              <RiskCount label="OT risk" value={riskMix.overtime} tone="ot" />
              <RiskCount label="Over" value={riskMix.high_ot} tone="danger" />
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">Role pressure</h2>
            <div className="mt-4 space-y-3">
              {rolePressure.length > 0 ? (
                rolePressure.map((item) => (
                  <RolePressureRow
                    key={item.license}
                    periodLabel={
                      view === "month"
                        ? "scheduled this month"
                        : "scheduled in selected period"
                    }
                    {...item}
                  />
                ))
              ) : (
                <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-sm text-slate-500">
                  No roles match the current rule view.
                </div>
              )}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-base font-semibold text-slate-950">
              Scheduler watch list
            </h2>
            <div className="mt-3 space-y-2">
              {employees.length > 0 ? (
                employees.slice(0, 5).map((employee) => (
                  <div
                    key={employee.employee_id}
                    className="flex items-start justify-between gap-3 rounded-md border border-slate-100 bg-slate-50 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-slate-950">
                        {employee.name}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {employee.license} - {employee.home_unit_id ?? "No home unit"}
                      </div>
                    </div>
                    <StatusBadge status={employeeStatus(employee, view, activePeriodKey)} />
                  </div>
                ))
              ) : (
                <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-sm text-slate-500">
                  No employees match the current rule view.
                </div>
              )}
            </div>
          </div>
        </aside>
      </section>

    </div>
  );
}

function ViewTabs({
  view,
  onChange,
}: {
  view: RuleView;
  onChange: (view: RuleView) => void;
}) {
  const tabs: { value: RuleView; label: string }[] = [
    { value: "weekly", label: "Weekly OT" },
    { value: "rn", label: "RN OT" },
    { value: "month", label: "Month balance" },
  ];
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          onClick={() => onChange(tab.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            view === tab.value
              ? "bg-white text-slate-950 shadow-sm"
              : "text-slate-600 hover:text-slate-950",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function WorkloadLegend() {
  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
      <LegendItem className="bg-emerald-700" label="Worked" />
      <LegendItem className="bg-teal-300" label="Scheduled" />
      <LegendItem className="bg-slate-100 ring-1 ring-slate-200" label="Still available" />
      <LegendItem className="bg-rose-500" label="Over limit" />
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-px bg-slate-800" />
        Rule limit
      </span>
    </div>
  );
}

function LegendItem({
  className,
  label,
}: {
  className: string;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-2.5 rounded-sm", className)} />
      {label}
    </span>
  );
}

function InsightCard({
  icon: Icon,
  label,
  value,
  detail,
  children,
  tone = "neutral",
}: {
  icon: typeof Users;
  label: string;
  value: string | number;
  detail: string;
  children?: ReactNode;
  tone?: CardTone;
}) {
  const toneClass = {
    neutral: "bg-slate-50 text-slate-700 ring-slate-200",
    warning: "bg-amber-50 text-amber-700 ring-amber-200",
    danger: "bg-rose-50 text-rose-700 ring-rose-200",
    capacity: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  }[tone];
  return (
    <div className="flex min-h-[164px] flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <div
          className={cn(
            "flex size-8 items-center justify-center rounded-md ring-1",
            toneClass,
          )}
        >
          <Icon className="size-4" />
        </div>
        <div className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
          {label}
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 tabular-nums">
        {value}
      </div>
      <div className="mt-1 text-sm text-slate-500">{detail}</div>
      {children ? <div className="mt-auto pt-3">{children}</div> : null}
    </div>
  );
}

function CoverageSignalStrip({
  loading,
  signals,
}: {
  loading: boolean;
  signals: { date: string; tone: CoverageTone }[];
}) {
  if (loading) {
    return (
      <div className="flex gap-1.5">
        {Array.from({ length: 7 }).map((_, index) => (
          <div
            key={index}
            className="h-2.5 flex-1 rounded-full bg-slate-100"
          />
        ))}
      </div>
    );
  }

  if (signals.length === 0) {
    return <div className="text-xs text-slate-400">Coverage feed unavailable</div>;
  }

  const toneClass: Record<CoverageTone, string> = {
    danger: "bg-rose-500",
    neutral: "bg-slate-200",
    safe: "bg-emerald-500",
    warning: "bg-amber-400",
  };

  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Daily coverage signal">
      {signals.slice(0, 14).map((signal) => (
        <div
          key={signal.date}
          className={cn("h-2.5 min-w-4 flex-1 rounded-full", toneClass[signal.tone])}
          title={`${shortDate(signal.date)} ${signal.tone}`}
        />
      ))}
    </div>
  );
}

function ConfirmationStack({ stats }: { stats: ConfirmationStats }) {
  if (stats.total === 0) {
    return <div className="text-xs text-slate-400">No confirmations in view</div>;
  }

  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="bg-emerald-500"
          style={{ width: `${percent(stats.accepted, stats.total)}%` }}
        />
        <div
          className="bg-amber-400"
          style={{ width: `${percent(stats.pending, stats.total)}%` }}
        />
        <div
          className="bg-slate-300"
          style={{ width: `${percent(stats.unsent, stats.total)}%` }}
        />
        <div
          className="bg-rose-500"
          style={{
            width: `${percent(stats.declined + stats.replaced, stats.total)}%`,
          }}
        />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-500">
        <span>{stats.actionNeeded} need response</span>
        <span>{stats.accepted} accepted</span>
      </div>
    </div>
  );
}

function RunwayStack({ stats }: { stats: RunwayStats }) {
  if (stats.total === 0) {
    return <div className="text-xs text-slate-400">No staff in view</div>;
  }

  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="bg-rose-500"
          style={{ width: `${percent(stats.over, stats.total)}%` }}
        />
        <div
          className="bg-orange-500"
          style={{ width: `${percent(stats.noRoom, stats.total)}%` }}
        />
        <div
          className="bg-amber-400"
          style={{ width: `${percent(stats.oneShift, stats.total)}%` }}
        />
        <div
          className="bg-sky-400"
          style={{ width: `${percent(stats.twoShifts, stats.total)}%` }}
        />
        <div
          className="bg-emerald-500"
          style={{ width: `${percent(stats.safe, stats.total)}%` }}
        />
      </div>
      <div className="mt-1.5 text-[11px] text-slate-500">
        {stats.close} at the one-shift cliff
      </div>
    </div>
  );
}

function ExceptionPreview({
  nextRisk,
  rows,
}: {
  nextRisk: NextRiskRow | undefined;
  rows: ExceptionRow[];
}) {
  if (rows.length === 0) {
    return (
      <div className="text-xs text-slate-500">
        {nextRisk
          ? `${nextRisk.employee.name}: ${Math.floor(nextRisk.runway)} safe shift${Math.floor(nextRisk.runway) === 1 ? "" : "s"} left`
          : "No staff currently under pressure"}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {rows.slice(0, 2).map((row) => (
        <div
          key={row.employee.employee_id}
          className="flex items-center justify-between gap-2 text-xs"
        >
          <span className="min-w-0 truncate font-medium text-slate-700">
            {row.employee.name}
          </span>
          <span className="shrink-0 text-rose-600">
            {STATUS_META[row.status].label}
          </span>
        </div>
      ))}
    </div>
  );
}

function CapacityByRole({
  byRole,
  total,
}: {
  byRole: Record<LicenseType, number>;
  total: number;
}) {
  if (total === 0) {
    return <div className="text-xs text-slate-400">No rule-safe whole shifts</div>;
  }

  const roles: LicenseType[] = ["RN", "LPN", "CNA", "PCT"];
  return (
    <div className="space-y-1.5">
      {roles
        .filter((license) => byRole[license] > 0)
        .slice(0, 3)
        .map((license) => (
          <div key={license} className="grid grid-cols-[36px_1fr_32px] items-center gap-2 text-[11px]">
            <span className="font-medium text-slate-600">{license}</span>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full bg-emerald-500"
                style={{ width: `${percent(byRole[license], total)}%` }}
              />
            </div>
            <span className="text-right tabular-nums text-slate-500">
              {byRole[license]}
            </span>
          </div>
        ))}
    </div>
  );
}

function RiskRow({
  employee,
  view,
  selectedPeriodKey,
}: {
  employee: EmployeeWorkHours;
  view: RuleView;
  selectedPeriodKey: string;
}) {
  const statusKey = employeeStatus(employee, view, selectedPeriodKey);
  const status = STATUS_META[statusKey];
  return (
    <div className="grid gap-3 px-4 py-4 lg:grid-cols-[260px_minmax(0,1fr)_180px] lg:items-center">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <div className="truncate text-sm font-semibold text-slate-950">
            {employee.name}
          </div>
          <Badge variant="outline" className="rounded-md">
            {employee.license}
          </Badge>
        </div>
        <div className="mt-1 text-xs text-slate-500">
          Home {employee.home_unit_id ?? "unassigned"} - {employee.scheduled_shifts} monthly shifts
        </div>
      </div>

      {view === "rn" ? (
        <RNCycleBar employee={employee} selectedPeriodKey={selectedPeriodKey} />
      ) : view === "weekly" ? (
        <WeeklyBar employee={employee} selectedPeriodKey={selectedPeriodKey} />
      ) : (
        <MonthBalanceBar employee={employee} />
      )}

      <div className="flex items-center justify-between gap-3 lg:justify-end">
        <div className={cn("text-sm font-semibold", status.text)}>
          {noteFor(employee, view, selectedPeriodKey)}
        </div>
        <StatusBadge status={statusKey} />
      </div>
    </div>
  );
}

function WeeklyBar({
  employee,
  selectedPeriodKey,
}: {
  employee: EmployeeWorkHours;
  selectedPeriodKey: string;
}) {
  const period = selectedPeriodForEmployee(
    employee,
    "weekly",
    selectedPeriodKey,
  );
  return (
    <SelectedPeriodBar
      period={period}
      thresholdLabel="weekly OT limit"
    />
  );
}

function RNCycleBar({
  employee,
  selectedPeriodKey,
}: {
  employee: EmployeeWorkHours;
  selectedPeriodKey: string;
}) {
  const period = selectedPeriodForEmployee(employee, "rn", selectedPeriodKey);
  return (
    <SelectedPeriodBar
      period={period}
      thresholdLabel="RN biweekly limit"
      showShiftCount
    />
  );
}

function SelectedPeriodBar({
  period,
  thresholdLabel,
  showShiftCount = false,
}: {
  period: WorkloadPeriod | null;
  thresholdLabel: string;
  showShiftCount?: boolean;
}) {
  if (!period) {
    return (
      <div className="rounded-md border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        No shifts in this rule period.
      </div>
    );
  }

  return (
    <PeriodBar
      period={period}
      thresholdLabel={thresholdLabel}
      showShiftCount={showShiftCount}
    />
  );
}

function PeriodBar({
  period,
  thresholdLabel,
  showShiftCount,
}: {
  period: WorkloadPeriod;
  thresholdLabel: string;
  showShiftCount: boolean;
}) {
  const stats = periodStats(period);
  const hasOverage = stats.over > 0 || period.double_shift_days > 0;
  return (
    <div
      className={cn(
        "rounded-md border px-2.5 py-2",
        hasOverage ? "border-rose-200 bg-rose-50/40" : "border-slate-100 bg-slate-50",
      )}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2 text-xs">
        <span className="font-medium text-slate-700">{periodRangeLabel(period)}</span>
        <span className="shrink-0 tabular-nums text-slate-500">
          {formatHours(stats.projected)} / {formatHours(stats.threshold)}
        </span>
      </div>
      <div
        className={cn(
          "relative h-3 overflow-hidden rounded-full border bg-white",
          hasOverage ? "border-rose-200" : "border-slate-200",
        )}
      >
        <div
          className="absolute inset-y-0 left-0 bg-emerald-700"
          style={{ width: `${stats.workedPct}%` }}
        />
        <div
          className="absolute inset-y-0 bg-teal-300"
          style={{
            left: `${stats.workedPct}%`,
            width: `${stats.scheduledPct}%`,
          }}
        />
        <div
          className="absolute inset-y-0 bg-slate-100"
          style={{
            left: `${stats.workedPct + stats.scheduledPct}%`,
            width: `${stats.remainingPct}%`,
          }}
        />
        {stats.over > 0 ? (
          <div
            className="absolute inset-y-0 bg-rose-500"
            style={{
              left: `${stats.thresholdPct}%`,
              width: `${stats.overPct}%`,
            }}
          />
        ) : null}
        <div
          className="absolute inset-y-0 w-px bg-slate-800"
          style={{ left: `${stats.thresholdPct}%` }}
          aria-label={thresholdLabel}
        />
      </div>
      <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[11px] text-slate-500">
        <span>{formatHours(stats.worked)} worked</span>
        <span>{formatHours(stats.scheduled)} scheduled</span>
        <span className={stats.over > 0 ? "font-semibold text-rose-600" : ""}>
          {stats.over > 0
            ? `${formatHours(stats.over)} over`
            : `${formatHours(stats.remaining)} remaining`}
        </span>
        {showShiftCount ? (
          <span
            className={
              period.projected_shifts > RN_BIWEEKLY_SHIFT_LIMIT
                ? "font-semibold text-rose-600"
                : ""
            }
          >
            {period.projected_shifts}/{RN_BIWEEKLY_SHIFT_LIMIT} shifts
          </span>
        ) : null}
        {period.double_shift_days > 0 ? (
          <span className="font-semibold text-rose-600">
            {period.double_shift_days} double day
            {period.double_shift_days === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function MonthBalanceBar({ employee }: { employee: EmployeeWorkHours }) {
  const actual = employee.worked_hours_this_month ?? 0;
  const scheduled = employee.scheduled_hours;
  const total = Math.max(1, actual + scheduled);
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-center justify-between text-xs text-slate-500">
        <span>Month workload</span>
        <span className="tabular-nums">
          {formatHours(actual)} worked - {formatHours(scheduled)} scheduled
        </span>
      </div>
      <div className="relative h-3 overflow-hidden rounded-full border border-slate-200 bg-slate-50">
        <div
          className="absolute inset-y-0 left-0 bg-sky-600"
          style={{ width: `${percent(actual, total)}%` }}
        />
        <div
          className="absolute inset-y-0 bg-cyan-300"
          style={{
            left: `${percent(actual, total)}%`,
            width: `${percent(scheduled, total)}%`,
          }}
        />
      </div>
      <div className="mt-1 text-[11px] text-slate-500">
        Monthly planning view. OT decisions use the weekly or RN rule tabs.
      </div>
    </div>
  );
}

function StatusBadge({
  status,
}: {
  status: EmployeeWorkHours["overtime_status"];
}) {
  const meta = STATUS_META[status];
  return (
    <Badge variant="outline" className={cn("rounded-md", meta.badge)}>
      {meta.label}
    </Badge>
  );
}

function RiskMixBar({
  counts,
}: {
  counts: Record<EmployeeWorkHours["overtime_status"], number>;
}) {
  const total = Math.max(1, Object.values(counts).reduce((sum, count) => sum + count, 0));
  return (
    <div className="mt-4 h-3 overflow-hidden rounded-full border border-slate-200 bg-slate-50">
      <div className="flex h-full">
        <div
          className="bg-emerald-500"
          style={{ width: `${percent(counts.healthy, total)}%` }}
        />
        <div
          className="bg-amber-400"
          style={{ width: `${percent(counts.near_ot, total)}%` }}
        />
        <div
          className="bg-orange-500"
          style={{ width: `${percent(counts.overtime, total)}%` }}
        />
        <div
          className="bg-rose-500"
          style={{ width: `${percent(counts.high_ot, total)}%` }}
        />
      </div>
    </div>
  );
}

function RiskCount({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "safe" | "warning" | "ot" | "danger";
}) {
  const dot = {
    safe: "bg-emerald-500",
    warning: "bg-amber-400",
    ot: "bg-orange-500",
    danger: "bg-rose-500",
  }[tone];
  return (
    <div className="flex items-center justify-between rounded-md border border-slate-100 px-2 py-1.5">
      <span className="inline-flex items-center gap-1.5 text-slate-600">
        <span className={cn("size-2 rounded-full", dot)} />
        {label}
      </span>
      <span className="font-semibold tabular-nums text-slate-950">{value}</span>
    </div>
  );
}

function RolePressureRow({
  license,
  count,
  risky,
  scheduled,
  periodLabel,
}: {
  license: LicenseType;
  count: number;
  risky: number;
  scheduled: number;
  periodLabel: string;
}) {
  const pct = count > 0 ? (risky / count) * 100 : 0;
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <div className="font-medium text-slate-900">{license}</div>
        <div className="text-xs text-slate-500">
          {risky} at risk / {count} staff
        </div>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={cn(
            "h-full",
            pct >= 45 ? "bg-rose-500" : pct >= 25 ? "bg-amber-400" : "bg-emerald-500",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1 text-[11px] text-slate-500">
        {formatHours(scheduled)} {periodLabel}
      </div>
    </div>
  );
}

function EmptyState({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: "neutral" | "danger";
}) {
  return (
    <div
      className={cn(
        "px-4 py-14 text-center text-sm",
        tone === "danger" ? "text-rose-600" : "text-slate-500",
      )}
    >
      {label}
    </div>
  );
}
