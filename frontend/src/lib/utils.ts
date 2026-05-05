import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

// First day of rotation #0. All 4-week schedule periods snap to a 28-day
// lattice anchored here, so e.g. rotation #1 starts 28 days later, rotation
// #2 another 28 days later, and so on. Jan 1, 2026 is a Thursday — periods
// therefore run Thu→Wed.
export const SCHEDULE_EPOCH = new Date(2026, 0, 1);
SCHEDULE_EPOCH.setHours(0, 0, 0, 0);

const PERIOD_DAYS = 28;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

// Returns the 4-week (28-day) schedule period containing `anchor`. Period
// boundaries are fixed to the SCHEDULE_EPOCH lattice — they don't shift to
// match the day of week of the picked anchor. The period whose range covers
// `anchor` is returned, even if `anchor` predates the epoch.
export function getFourWeekSchedulePeriod(anchor: Date): {
  start: Date;
  end: Date;
} {
  const a = new Date(anchor);
  a.setHours(0, 0, 0, 0);
  const daysFromEpoch = Math.floor(
    (a.getTime() - SCHEDULE_EPOCH.getTime()) / MS_PER_DAY,
  );
  const rotationIndex = Math.floor(daysFromEpoch / PERIOD_DAYS);
  const start = new Date(SCHEDULE_EPOCH);
  start.setDate(SCHEDULE_EPOCH.getDate() + rotationIndex * PERIOD_DAYS);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(start.getDate() + PERIOD_DAYS - 1);
  end.setHours(23, 59, 59, 999);
  return { start, end };
}

export function formatPeriodRange(start: Date, end: Date): string {
  const sameYear = start.getFullYear() === end.getFullYear();
  const sameMonth = sameYear && start.getMonth() === end.getMonth();
  if (sameMonth) {
    return `${MONTH_SHORT[start.getMonth()]} ${start.getDate()} – ${end.getDate()}, ${start.getFullYear()}`;
  }
  if (sameYear) {
    return `${MONTH_SHORT[start.getMonth()]} ${start.getDate()} – ${MONTH_SHORT[end.getMonth()]} ${end.getDate()}, ${start.getFullYear()}`;
  }
  return `${MONTH_SHORT[start.getMonth()]} ${start.getDate()}, ${start.getFullYear()} – ${MONTH_SHORT[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
}

// YYYY-MM-DD in the local timezone (matches backend's date-only fields).
export function toDateKey(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
