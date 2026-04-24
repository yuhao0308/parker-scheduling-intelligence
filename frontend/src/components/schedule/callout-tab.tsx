"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCalloutsByMonth } from "@/lib/queries";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

interface CalloutTabProps {
  year: number;
  month: number;
}

/**
 * Mini-calendar view in the right-column Callout tab.
 *
 * Days with an *active* (unfilled) callout display a red dot. Clicking the day
 * deep-links into the /callout form with `date` prefilled. A secondary "File a
 * callout" button opens the form with no parameters for the standard flow.
 */
export function CalloutTab({ year, month }: CalloutTabProps) {
  const router = useRouter();
  const monthStr = `${year}-${String(month).padStart(2, "0")}`;
  const { data: rollup = [] } = useCalloutsByMonth(monthStr);

  const byDate = new Map(rollup.map((r) => [r.date, r]));

  // Build month grid
  const firstDow = new Date(year, month - 1, 1).getDay();
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells: ({ day: number; date: string } | null)[] = [];
  for (let i = 0; i < firstDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    const date = `${year}-${String(month).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, date });
  }
  while (cells.length % 7 !== 0) cells.push(null);

  function goToCalloutForm(date?: string) {
    const qs = date ? `?date=${encodeURIComponent(date)}` : "";
    router.push(`/callout${qs}`);
  }

  const activeDays = rollup.filter((r) => r.active > 0).length;

  return (
    <div className="space-y-3">
      <div className="text-xs text-muted-foreground">
        Red dots mark days with open call-outs. Click a day to report a
        callout prefilled with that date.
      </div>

      {/* Weekday header */}
      <div className="grid grid-cols-7 text-center text-[10px] font-semibold text-muted-foreground">
        {WEEKDAYS.map((d, i) => (
          <div key={i}>{d}</div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, idx) => {
          if (!cell) {
            return <div key={`empty-${idx}`} className="aspect-square" />;
          }
          const info = byDate.get(cell.date);
          const hasActive = (info?.active ?? 0) > 0;
          const hasResolved = (info?.total ?? 0) > (info?.active ?? 0);
          return (
            <button
              key={cell.date}
              type="button"
              onClick={() => goToCalloutForm(cell.date)}
              className={cn(
                "relative aspect-square rounded-md border text-xs font-medium transition",
                "hover:bg-accent hover:border-accent-foreground/40",
                hasActive
                  ? "border-red-300 bg-red-50 text-red-900"
                  : "border-transparent bg-muted/30 text-muted-foreground",
              )}
              title={
                info
                  ? `${info.active} active / ${info.total} total callout${info.total === 1 ? "" : "s"}`
                  : "Report a call-out for this day"
              }
            >
              <span>{cell.day}</span>
              {hasActive && (
                <span
                  aria-label={`${info?.active} active callouts`}
                  className="absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full bg-red-500"
                />
              )}
              {!hasActive && hasResolved && (
                <span
                  aria-label={`${info?.total} resolved callouts`}
                  className="absolute top-0.5 right-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400"
                />
              )}
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between border-t pt-3">
        <div className="text-xs text-muted-foreground">
          {activeDays === 0
            ? "No active callouts this month"
            : `${activeDays} day${activeDays === 1 ? "" : "s"} with active callouts`}
        </div>
        <Button size="sm" onClick={() => goToCalloutForm()}>
          Report a call-out
        </Button>
      </div>
    </div>
  );
}
