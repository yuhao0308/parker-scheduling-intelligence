"use client";

import { cn } from "@/lib/utils";
import type { ConfirmationStatus } from "@/lib/types";

// Operator-facing color language (supervisor mockups):
//   gray  = UNSENT   — scheduled but confirmation not yet sent
//   yellow= PENDING  — confirmation sent, awaiting reply
//   green = ACCEPTED — nurse accepted
//   red   = DECLINED — nurse declined; needs remove / replace
//   slate = REPLACED — slot cleared (manually removed or replaced)
const ORB_CLASSES: Record<ConfirmationStatus, string> = {
  UNSENT: "bg-slate-300",
  PENDING: "bg-amber-400",
  ACCEPTED: "bg-emerald-500",
  DECLINED: "bg-red-500",
  REPLACED: "bg-slate-400",
};

const ORB_LABEL: Record<ConfirmationStatus, string> = {
  UNSENT: "Not sent",
  PENDING: "Awaiting reply",
  ACCEPTED: "Accepted",
  DECLINED: "Declined",
  REPLACED: "Replaced / removed",
};

interface StatusOrbProps {
  status: ConfirmationStatus | null | undefined;
  size?: "sm" | "md";
  className?: string;
}

/** Colored dot beside an employee name, keyed off confirmation status. */
export function StatusOrb({ status, size = "sm", className }: StatusOrbProps) {
  const resolved: ConfirmationStatus = status ?? "UNSENT";
  const dim = size === "md" ? "h-3 w-3" : "h-2.5 w-2.5";
  return (
    <span
      aria-label={ORB_LABEL[resolved]}
      title={ORB_LABEL[resolved]}
      className={cn(
        "inline-block rounded-full shrink-0",
        dim,
        ORB_CLASSES[resolved],
        className,
      )}
    />
  );
}

export { ORB_LABEL as STATUS_ORB_LABELS };
