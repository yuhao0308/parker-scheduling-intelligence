"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  ShiftLabel,
  ShiftSlot,
  ShiftSlotStatus,
} from "@/lib/types";

const SHIFT_ORDER: Array<{ key: ShiftLabel; label: string }> = [
  { key: "DAY", label: "Day" },
  { key: "EVENING", label: "Evening" },
  { key: "NIGHT", label: "Night" },
];

const STATUS_BADGE: Record<ShiftSlotStatus, { label: string; className: string }> = {
  fully_staffed: {
    label: "Fully Staffed",
    className: "bg-emerald-100 text-emerald-800 border-emerald-300",
  },
  partially_staffed: {
    label: "Partially Staffed",
    className: "bg-amber-100 text-amber-800 border-amber-300",
  },
  unassigned: {
    label: "Unassigned",
    className: "bg-slate-100 text-slate-700 border-slate-300",
  },
};

interface DayDetailDialogProps {
  date: string | null;
  slots: ShiftSlot[];
  selectedUnit: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenShift: (slots: ShiftSlot[]) => void;
}

interface ShiftSection {
  shift: ShiftLabel;
  label: string;
  slots: ShiftSlot[];
  assigned: number;
  pending: number;
  required: number;
  status: ShiftSlotStatus;
}

function buildSections(
  slots: ShiftSlot[],
  selectedUnit: string | null,
): ShiftSection[] {
  return SHIFT_ORDER.map(({ key, label }) => {
    const scoped = slots.filter(
      (s) => s.shift_label === key && (!selectedUnit || s.unit_id === selectedUnit),
    );
    const allEmployees = scoped.flatMap((s) => s.assigned_employees);
    const assigned = allEmployees.filter(
      (e) => e.confirmation_status === "ACCEPTED",
    ).length;
    const pending = allEmployees.filter(
      (e) => e.confirmation_status === "PENDING",
    ).length;
    const required = scoped.reduce((n, s) => n + s.required_count, 0);

    let status: ShiftSlotStatus;
    if (scoped.length === 0 || (assigned === 0 && required > 0)) {
      status = "unassigned";
    } else if (required > 0 && assigned >= required) {
      status = "fully_staffed";
    } else {
      status = "partially_staffed";
    }

    return { shift: key, label, slots: scoped, assigned, pending, required, status };
  });
}

function formatDate(date: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function DayDetailDialog({
  date,
  slots,
  selectedUnit,
  open,
  onOpenChange,
  onOpenShift,
}: DayDetailDialogProps) {
  if (!date) return null;
  const sections = buildSections(slots, selectedUnit);
  const totalRequired = sections.reduce((n, s) => n + s.required, 0);
  const totalAssigned = sections.reduce((n, s) => n + s.assigned, 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl w-[95vw] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{formatDate(date)}</DialogTitle>
          <DialogDescription>
            {selectedUnit ? `Unit ${selectedUnit}` : "All units"} ·{" "}
            {totalAssigned}/{totalRequired} confirmed across all shifts
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {sections.map((section) => {
            const badge = STATUS_BADGE[section.status];
            const isEmpty = section.slots.length === 0;
            return (
              <div
                key={section.shift}
                className={cn(
                  "rounded-lg border p-3 space-y-2",
                  isEmpty && "bg-muted/30",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{section.label} Shift</span>
                    <Badge
                      variant="secondary"
                      className={cn("border", badge.className)}
                    >
                      {badge.label}
                    </Badge>
                    {!isEmpty && (
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {section.assigned}/{section.required} confirmed
                        {section.pending > 0 && ` · ${section.pending} pending`}
                      </span>
                    )}
                  </div>
                  {!isEmpty && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1"
                      onClick={() => onOpenShift(section.slots)}
                    >
                      Details
                      <ChevronRight className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>

                {isEmpty ? (
                  <p className="text-xs text-muted-foreground">
                    No shifts scheduled for this period.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {section.slots.flatMap((slot) =>
                      slot.assigned_employees.map((e) => {
                        const pendingCls =
                          e.confirmation_status === "PENDING"
                            ? "bg-amber-50 text-amber-800 border-amber-300"
                            : e.confirmation_status === "DECLINED"
                              ? "bg-red-50 text-red-700 border-red-300"
                              : "";
                        return (
                          <Badge
                            key={`${slot.unit_id}-${e.employee_id}`}
                            variant="outline"
                            className={cn("text-xs", pendingCls)}
                          >
                            {e.name} ({e.license})
                            {!selectedUnit && (
                              <span className="ml-1 text-muted-foreground">
                                · {slot.unit_id}
                              </span>
                            )}
                          </Badge>
                        );
                      }),
                    )}
                    {section.slots.every(
                      (s) => s.assigned_employees.length === 0,
                    ) && (
                      <span className="text-xs text-muted-foreground">
                        No one assigned yet.
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
