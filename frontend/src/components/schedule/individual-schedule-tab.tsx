"use client";

import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAllActiveStaff } from "@/lib/queries";
import { cn } from "@/lib/utils";
import type { StaffOut } from "@/lib/types";

interface IndividualScheduleTabProps {
  selectedEmployeeIds: Set<string>;
  onSelectedEmployeeIdsChange: (next: Set<string>) => void;
}

const LICENSE_BADGE: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800 border-blue-200",
  LPN: "bg-green-100 text-green-800 border-green-200",
  CNA: "bg-amber-100 text-amber-800 border-amber-200",
  PCT: "bg-purple-100 text-purple-800 border-purple-200",
};

export function IndividualScheduleTab({
  selectedEmployeeIds,
  onSelectedEmployeeIdsChange,
}: IndividualScheduleTabProps) {
  const { data: staff = [], isLoading } = useAllActiveStaff();
  const [search, setSearch] = useState("");

  const filteredStaff = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return staff;
    return staff.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.employee_id.toLowerCase().includes(q) ||
        s.license.toLowerCase().includes(q),
    );
  }, [staff, search]);

  const grouped = useMemo(() => groupByLicense(filteredStaff), [filteredStaff]);

  function toggle(id: string) {
    const next = new Set(selectedEmployeeIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedEmployeeIdsChange(next);
  }

  function clearAll() {
    onSelectedEmployeeIdsChange(new Set());
  }

  return (
    <div className="flex flex-col gap-2 min-h-[24rem]">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Individual Schedule</h3>
          <p className="text-[11px] text-muted-foreground">
            Filter the calendar by one or more employees.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {selectedEmployeeIds.size > 0 && (
            <Badge
              variant="secondary"
              className="bg-primary/10 text-primary border-primary/20 text-[10px]"
            >
              {selectedEmployeeIds.size} selected
            </Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={selectedEmployeeIds.size === 0}
            onClick={clearAll}
            className="h-7 px-2 text-xs"
          >
            Clear All
          </Button>
        </div>
      </div>

      <div className="relative">
        <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name, ID, or license"
          className="w-full rounded-md border bg-background pl-7 pr-7 py-1.5 text-sm"
        />
        {search && (
          <button
            type="button"
            onClick={() => setSearch("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="Clear search"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto rounded-md border bg-card max-h-[28rem]">
        {isLoading ? (
          <div className="p-4 text-xs text-muted-foreground">Loading staff…</div>
        ) : filteredStaff.length === 0 ? (
          <div className="p-4 text-xs text-muted-foreground">No matches.</div>
        ) : (
          grouped.map((group) => (
            <div key={group.license}>
              <div className="sticky top-0 z-10 flex items-center justify-between bg-muted/60 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border-b">
                <span>{group.license}</span>
                <span>{group.staff.length}</span>
              </div>
              {group.staff.map((s) => {
                const checked = selectedEmployeeIds.has(s.employee_id);
                return (
                  <label
                    key={s.employee_id}
                    className={cn(
                      "flex items-center gap-2 px-2 py-1.5 text-sm cursor-pointer hover:bg-muted/40 border-b last:border-b-0",
                      checked && "bg-primary/5",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(s.employee_id)}
                      className="h-3.5 w-3.5"
                    />
                    <span className="flex-1 truncate">{s.name}</span>
                    <Badge
                      variant="secondary"
                      className={cn(
                        "text-[10px] px-1.5 py-0 border",
                        LICENSE_BADGE[s.license] ?? "",
                      )}
                    >
                      {s.license}
                    </Badge>
                    {s.home_unit_id && (
                      <span className="text-[10px] text-muted-foreground">
                        {s.home_unit_id}
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function groupByLicense(staff: StaffOut[]): { license: string; staff: StaffOut[] }[] {
  const order = ["RN", "LPN", "CNA", "PCT"];
  const map = new Map<string, StaffOut[]>();
  for (const s of staff) {
    const key = s.license || "Other";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(s);
  }
  const groups: { license: string; staff: StaffOut[] }[] = [];
  for (const k of order) {
    if (map.has(k)) {
      groups.push({ license: k, staff: map.get(k)!.sort(byName) });
      map.delete(k);
    }
  }
  for (const [k, list] of map) {
    groups.push({ license: k, staff: list.sort(byName) });
  }
  return groups;
}

function byName(a: StaffOut, b: StaffOut) {
  return a.name.localeCompare(b.name);
}
