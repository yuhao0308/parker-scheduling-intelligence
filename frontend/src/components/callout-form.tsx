"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useMonthlySchedule, useUnits } from "@/lib/queries";
import {
  typologyLabel,
  type CalloutRequest,
  type ShiftLabel,
  type UnitOut,
} from "@/lib/types";
import {
  Building2,
  CalendarDays,
  ArrowRight,
  Check,
  Loader2,
  UserX,
  Users,
} from "lucide-react";

interface CalloutFormInitialValues {
  unit_id?: string;
  shift_label?: ShiftLabel;
  shift_date?: string;
  employee_id?: string;
}

interface CalloutFormProps {
  onSubmit: (req: CalloutRequest) => void;
  isPending: boolean;
  initialValues?: CalloutFormInitialValues;
}

const SHIFT_OPTIONS: {
  value: ShiftLabel;
  label: string;
  hours: string;
  activeClass: string;
}[] = [
  {
    value: "DAY",
    label: "Day",
    hours: "7a – 3p",
    activeClass: "border-amber-400 bg-amber-50 text-amber-900",
  },
  {
    value: "EVENING",
    label: "Evening",
    hours: "3p – 11p",
    activeClass: "border-violet-400 bg-violet-50 text-violet-900",
  },
  {
    value: "NIGHT",
    label: "Night",
    hours: "11p – 7a",
    activeClass: "border-slate-500 bg-slate-100 text-slate-900",
  },
];

const LICENSE_BADGE: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800",
  LPN: "bg-green-100 text-green-800",
  CNA: "bg-amber-100 text-amber-800",
  PCT: "bg-purple-100 text-purple-800",
};

export function CalloutForm({
  onSubmit,
  isPending,
  initialValues,
}: CalloutFormProps) {
  const today = useMemo(() => new Date().toISOString().split("T")[0], []);
  const [unitId, setUnitId] = useState<string | null>(
    initialValues?.unit_id ?? null,
  );
  const [shiftLabel, setShiftLabel] = useState<ShiftLabel>(
    initialValues?.shift_label ?? "DAY",
  );
  const [shiftDate, setShiftDate] = useState(
    initialValues?.shift_date ?? today,
  );
  const [employeeId, setEmployeeId] = useState<string | null>(
    initialValues?.employee_id ?? null,
  );

  const { data: units, isLoading: unitsLoading } = useUnits();
  const selectedMonth = useMemo(() => {
    const [yearRaw, monthRaw] = shiftDate.split("-");
    const year = Number(yearRaw);
    const month = Number(monthRaw);
    if (Number.isFinite(year) && Number.isFinite(month)) {
      return { year, month };
    }
    const fallback = new Date(`${today}T00:00:00`);
    return { year: fallback.getFullYear(), month: fallback.getMonth() + 1 };
  }, [shiftDate, today]);

  const { data: monthlySchedule, isLoading: slotStaffLoading } =
    useMonthlySchedule(selectedMonth.year, selectedMonth.month);

  const slotStaff = useMemo(() => {
    if (!unitId || !shiftDate || !monthlySchedule) return [];
    const day = monthlySchedule.days.find((entry) => entry.date === shiftDate);
    const slot = day?.slots.find(
      (entry) => entry.unit_id === unitId && entry.shift_label === shiftLabel,
    );
    if (!slot) return [];
    const seen = new Set<string>();
    return slot.assigned_employees
      .filter((e) => e.confirmation_status !== "DECLINED")
      .filter((e) => {
        if (seen.has(e.employee_id)) return false;
        seen.add(e.employee_id);
        return true;
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [monthlySchedule, shiftDate, shiftLabel, unitId]);

  useEffect(() => {
    if (slotStaffLoading) return;
    if (!employeeId) return;
    if (slotStaff.some((e) => e.employee_id === employeeId)) return;
    setEmployeeId(null);
  }, [employeeId, slotStaff, slotStaffLoading]);

  const canSubmit = unitId && employeeId && shiftDate && !isPending;

  function handleSubmit() {
    if (!unitId || !employeeId) return;
    onSubmit({
      callout_employee_id: employeeId,
      unit_id: unitId,
      shift_date: shiftDate,
      shift_label: shiftLabel,
    });
  }

  const selectedEmployee = slotStaff.find((e) => e.employee_id === employeeId);

  return (
    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
      {/* Header */}
      <div className="border-b bg-muted/40 px-6 py-5">
        <h2 className="text-base font-semibold">Report a Call-Out</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Enter shift details to find the best available replacements.
        </p>
      </div>

      <div className="p-6 space-y-6">
        {/* Row 1: Unit + Date */}
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-2">
            <Label className="flex items-center gap-1.5 text-sm font-medium">
              <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
              Unit
            </Label>
            <UnitPicker
              units={units ?? []}
              loading={unitsLoading}
              selectedId={unitId}
              onSelect={(nextUnitId) => {
                setUnitId(nextUnitId);
                setEmployeeId(null);
              }}
            />
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-1.5 text-sm font-medium">
              <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
              Shift Date
            </Label>
            <Input
              type="date"
              value={shiftDate}
              onChange={(e) => setShiftDate(e.target.value)}
              className="h-10"
            />
          </div>
        </div>

        {/* Row 2: Shift toggle */}
        <div className="space-y-2">
          <Label className="text-sm font-medium">Shift</Label>
          <div className="grid grid-cols-3 gap-2 sm:w-72">
            {SHIFT_OPTIONS.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => setShiftLabel(s.value)}
                className={cn(
                  "flex flex-col items-center justify-center rounded-lg border-2 px-3 py-2.5 font-medium transition-all cursor-pointer",
                  shiftLabel === s.value
                    ? s.activeClass
                    : "border-transparent bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                <span className="font-semibold text-[13px]">{s.label}</span>
                <span className="text-[10px] mt-0.5 font-normal opacity-70">
                  {s.hours}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Row 3: Inline employee picker */}
        <EmployeePicker
          unitId={unitId}
          loading={slotStaffLoading}
          employees={slotStaff}
          selectedId={employeeId}
          onSelect={setEmployeeId}
        />

        {/* Submit */}
        <Button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="w-full h-11 font-semibold gap-2"
          size="lg"
        >
          {isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Finding Replacements…
            </>
          ) : (
            <>
              {selectedEmployee
                ? `Find Replacements for ${selectedEmployee.name}`
                : "Find Replacements"}
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

/* ── Inline unit picker ─────────────────────────────────────────────────── */

interface UnitPickerProps {
  units: UnitOut[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function UnitPicker({ units, loading, selectedId, onSelect }: UnitPickerProps) {
  if (loading) {
    return (
      <div className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-10 rounded-lg border border-transparent bg-muted/40 animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
      {units.map((unit) => {
        const isSelected = selectedId === unit.unit_id;
        return (
          <button
            key={unit.unit_id}
            type="button"
            onClick={() => onSelect(unit.unit_id)}
            className={cn(
              "group flex min-w-0 items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition-all",
              isSelected
                ? "border-primary/60 bg-primary/5 shadow-sm"
                : "border-border/70 bg-background hover:border-muted-foreground/30 hover:bg-muted/35",
            )}
          >
            <span
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-all",
                isSelected
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-muted-foreground/25 text-transparent group-hover:border-muted-foreground/45",
              )}
            >
              <Check className="h-3 w-3" />
            </span>
            <span className="min-w-0 flex-1">
              <span
                className={cn(
                  "block truncate text-sm font-medium leading-tight",
                  isSelected ? "text-primary" : "text-foreground",
                )}
              >
                {unit.name}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {typologyLabel(unit.typology)}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* ── Inline employee picker ─────────────────────────────────────────────── */

interface Employee {
  employee_id: string;
  name: string;
  license: string;
}

interface EmployeePickerProps {
  unitId: string | null;
  loading: boolean;
  employees: Employee[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

function EmployeePicker({
  unitId,
  loading,
  employees,
  selectedId,
  onSelect,
}: EmployeePickerProps) {
  return (
    <div className="space-y-2">
      <Label className="flex items-center gap-1.5 text-sm font-medium">
        <UserX className="h-3.5 w-3.5 text-muted-foreground" />
        Who Called Out?
      </Label>

      {/* Placeholder states */}
      {!unitId ? (
        <EmptyState icon={<Building2 className="h-4 w-4" />}>
          Select a unit to see assigned staff
        </EmptyState>
      ) : loading ? (
        <LoadingState />
      ) : employees.length === 0 ? (
        <EmptyState icon={<Users className="h-4 w-4" />}>
          No staff assigned to this unit, date &amp; shift
        </EmptyState>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {employees.map((e) => {
            const isSelected = selectedId === e.employee_id;
            return (
              <button
                key={e.employee_id}
                type="button"
                onClick={() => onSelect(isSelected ? null : e.employee_id)}
                className={cn(
                  "flex min-w-0 flex-col items-start gap-1.5 rounded-lg border-2 px-2.5 py-2 text-left transition-all cursor-pointer",
                  isSelected
                    ? "border-primary bg-primary/5 shadow-sm"
                    : "border-transparent bg-muted/40 hover:bg-muted hover:border-muted-foreground/20",
                )}
              >
                {/* Selection dot */}
                <div className="flex w-full items-center justify-between">
                  <span
                    className={cn(
                      "inline-flex items-center justify-center rounded-full w-4 h-4 border-2 transition-all shrink-0",
                      isSelected
                        ? "border-primary bg-primary"
                        : "border-muted-foreground/30 bg-transparent",
                    )}
                  >
                    {isSelected && (
                      <span className="block w-1.5 h-1.5 rounded-full bg-white" />
                    )}
                  </span>
                  <span
                    className={cn(
                      "text-[10px] font-semibold rounded px-1.5 py-0.5",
                      LICENSE_BADGE[e.license] ?? "bg-muted text-muted-foreground",
                    )}
                  >
                    {e.license}
                  </span>
                </div>
                <span
                  className={cn(
                    "line-clamp-2 text-sm font-medium leading-tight",
                    isSelected ? "text-primary" : "text-foreground",
                  )}
                >
                  {e.name}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EmptyState({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-dashed bg-muted/20 px-4 py-3.5 text-sm text-muted-foreground">
      <span className="text-muted-foreground/60">{icon}</span>
      {children}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="h-[68px] rounded-lg border-2 border-transparent bg-muted/40 animate-pulse"
        />
      ))}
    </div>
  );
}
