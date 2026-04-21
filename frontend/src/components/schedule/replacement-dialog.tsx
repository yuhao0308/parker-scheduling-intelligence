"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { CandidateList } from "@/components/candidate-list";
import { FilterStatsBadge } from "@/components/filter-stats-badge";
import { useRemoveEntry, useReplaceEntry } from "@/lib/queries";
import type {
  CalloutResponse,
  ConfirmationEntry,
  ScoredCandidate,
} from "@/lib/types";

interface ReplacementDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entry: ConfirmationEntry | null;
  replacement: CalloutResponse | null;
  weekStart: string;
  onReplaced: () => void;
}

export function ReplacementDialog({
  open,
  onOpenChange,
  entry,
  replacement,
  weekStart,
  onReplaced,
}: ReplacementDialogProps) {
  const replaceMutation = useReplaceEntry(weekStart);
  const removeMutation = useRemoveEntry(weekStart);

  function handleRemoveInstead() {
    if (!entry) return;
    removeMutation.mutate(entry.entry_id, {
      onSuccess: () => {
        onOpenChange(false);
        onReplaced();
      },
    });
  }

  function handleSelect(candidate: ScoredCandidate) {
    if (!entry || !replacement) return;
    replaceMutation.mutate(
      {
        entryId: entry.entry_id,
        req: {
          recommendation_log_id: replacement.recommendation_log_id,
          selected_employee_id: candidate.employee_id,
          selected_rank: candidate.rank,
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          onReplaced();
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Pick a replacement</DialogTitle>
          <DialogDescription>
            {entry && replacement ? (
              <>
                {entry.name} declined {replacement.shift_label} on{" "}
                {replacement.shift_date} at {replacement.unit_name}. Select a
                replacement below.
              </>
            ) : (
              "Loading candidates…"
            )}
          </DialogDescription>
        </DialogHeader>

        {replacement && (
          <div className="space-y-3">
            <FilterStatsBadge stats={replacement.filter_stats} />
            <CandidateList
              candidates={replacement.candidates}
              onSelect={handleSelect}
              disabled={replaceMutation.isPending || removeMutation.isPending}
            />
            {replaceMutation.isError && (
              <div className="text-sm text-destructive">
                {(replaceMutation.error as Error)?.message ?? "Replacement failed."}
              </div>
            )}
            {removeMutation.isError && (
              <div className="text-sm text-destructive">
                {(removeMutation.error as Error)?.message ?? "Remove failed."}
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleRemoveInstead}
            disabled={
              !entry ||
              replaceMutation.isPending ||
              removeMutation.isPending
            }
            title="Skip replacement: clear this slot and return the nurse to the pool picker"
          >
            {removeMutation.isPending ? "Removing…" : "Remove instead"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
