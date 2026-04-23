"use client";

import { StatusOrb } from "@/components/schedule/status-orb";
import type { ConfirmationEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ShiftRowProps {
  entry: ConfirmationEntry;
  employeeName: string;
  confirmationLabel: string;
  // Manual review intent: true = keep assignment, false = reopen into pool.
  // Only meaningful while the entry is PENDING; ignored otherwise.
  intent: boolean;
  onIntentChange: (next: boolean) => void;
  disabled: boolean;
}

function formatSlot(entry: ConfirmationEntry): string {
  const d = new Date(`${entry.shift_date}T00:00:00`);
  const dow = d.toLocaleDateString(undefined, { weekday: "short" });
  const md = `${d.getMonth() + 1}/${d.getDate()}`;
  return `${dow} ${md} · ${entry.unit_id} · ${entry.shift_label}`;
}

export function ShiftRow({
  entry,
  employeeName,
  confirmationLabel,
  intent,
  onIntentChange,
  disabled,
}: ShiftRowProps) {
  const status = entry.confirmation_status;
  const isPending = status === "PENDING";

  return (
    <div className="flex items-center gap-2 pl-8 pr-3 py-1 text-[11px]">
      <StatusOrb status={status} />
      <div className="min-w-0 flex-1 truncate text-muted-foreground tabular-nums">
        {formatSlot(entry)}
      </div>
      {isPending ? (
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            className={cn(
              "inline-flex h-6 min-w-[84px] items-center justify-center rounded-full border px-2.5 text-[10px] font-semibold tracking-wide transition-colors",
              intent
                ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                : "border-red-200 bg-red-50 text-red-700 hover:bg-red-100",
              disabled && "cursor-not-allowed opacity-60 hover:bg-inherit",
            )}
            title={
              intent
                ? "Keep: this shift stays assigned to the current employee."
                : "Reopen: remove this shift from the current employee and put it back into the pool."
            }
            aria-pressed={intent}
            aria-label={`${intent ? "Keep" : "Reopen"} ${formatSlot(entry)} for ${employeeName}`}
            disabled={disabled}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onIntentChange(!intent);
            }}
          >
            {intent ? "Keep" : "Reopen"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
