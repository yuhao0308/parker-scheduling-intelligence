"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useUnits, useStaffForUnit } from "@/lib/queries";
import { typologyLabel, type CalloutRequest, type ShiftLabel } from "@/lib/types";

interface CalloutFormProps {
  onSubmit: (req: CalloutRequest) => void;
  isPending: boolean;
}

export function CalloutForm({ onSubmit, isPending }: CalloutFormProps) {
  const [unitId, setUnitId] = useState<string | null>(null);
  const [shiftLabel, setShiftLabel] = useState<ShiftLabel>("DAY");
  const [shiftDate, setShiftDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [employeeId, setEmployeeId] = useState<string | null>(null);

  const { data: units, isLoading: unitsLoading } = useUnits();
  const { data: staff, isLoading: staffLoading } = useStaffForUnit(unitId);

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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Report Call-Out</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Unit</Label>
            <Select
              value={unitId ?? ""}
              onValueChange={(v) => {
                setUnitId(v);
                setEmployeeId(null);
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder={unitsLoading ? "Loading..." : "Select unit"} />
              </SelectTrigger>
              <SelectContent>
                {units?.map((u) => (
                  <SelectItem key={u.unit_id} value={u.unit_id}>
                    {u.name} ({typologyLabel(u.typology)})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Employee Who Called Out</Label>
            <Select
              value={employeeId ?? ""}
              onValueChange={setEmployeeId}
              disabled={!unitId}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    !unitId
                      ? "Select a unit first"
                      : staffLoading
                        ? "Loading..."
                        : "Select employee"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {staff?.map((s) => (
                  <SelectItem key={s.employee_id} value={s.employee_id}>
                    {s.name} ({s.license})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Shift Date</Label>
            <Input
              type="date"
              value={shiftDate}
              onChange={(e) => setShiftDate(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>Shift</Label>
            <RadioGroup
              value={shiftLabel}
              onValueChange={(v) => setShiftLabel(v as ShiftLabel)}
              className="flex gap-4 pt-2"
            >
              {(["DAY", "EVENING", "NIGHT"] as const).map((s) => (
                <div key={s} className="flex items-center gap-1.5">
                  <RadioGroupItem value={s} id={`shift-${s}`} />
                  <Label htmlFor={`shift-${s}`} className="font-normal cursor-pointer">
                    {s}
                  </Label>
                </div>
              ))}
            </RadioGroup>
          </div>
        </div>

        <Button onClick={handleSubmit} disabled={!canSubmit} className="w-full">
          {isPending ? "Getting Recommendations..." : "Get Recommendations"}
        </Button>
      </CardContent>
    </Card>
  );
}
