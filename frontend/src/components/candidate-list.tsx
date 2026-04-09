"use client";

import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CandidateRow } from "./candidate-row";
import type { ScoredCandidate } from "@/lib/types";

interface CandidateListProps {
  candidates: ScoredCandidate[];
  onSelect: (candidate: ScoredCandidate) => void;
  disabled: boolean;
}

export function CandidateList({ candidates, onSelect, disabled }: CandidateListProps) {
  if (candidates.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No eligible candidates found after filtering.
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-16">Rank</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>License</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Home Unit</TableHead>
          <TableHead>Score</TableHead>
          <TableHead>Breakdown</TableHead>
          <TableHead className="w-32">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {candidates.map((candidate) => (
          <CandidateRow
            key={candidate.employee_id}
            candidate={candidate}
            onSelect={onSelect}
            disabled={disabled}
          />
        ))}
      </TableBody>
    </Table>
  );
}
