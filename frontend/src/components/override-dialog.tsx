"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ScoredCandidate } from "@/lib/types";

interface OverrideDialogProps {
  candidate: ScoredCandidate | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string) => void;
  isPending: boolean;
}

export function OverrideDialog({
  candidate,
  open,
  onOpenChange,
  onConfirm,
  isPending,
}: OverrideDialogProps) {
  const [reason, setReason] = useState("");

  if (!candidate) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Override Selection</DialogTitle>
          <DialogDescription>
            You are selecting <strong>{candidate.name}</strong> (rank #{candidate.rank})
            instead of the top recommendation. Please provide a reason.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="override-reason">Reason</Label>
          <Input
            id="override-reason"
            placeholder="e.g., Staff member already confirmed availability"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onConfirm(reason);
              setReason("");
            }}
            disabled={!reason.trim() || isPending}
          >
            {isPending ? "Submitting..." : "Confirm Selection"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
