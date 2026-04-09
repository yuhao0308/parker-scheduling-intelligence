"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import { ScoreBreakdown } from "./score-breakdown";
import type { ScoredCandidate } from "@/lib/types";

const licenseBadgeColor: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800",
  LPN: "bg-green-100 text-green-800",
  CNA: "bg-amber-100 text-amber-800",
  PCT: "bg-purple-100 text-purple-800",
};

interface CandidateRowProps {
  candidate: ScoredCandidate;
  onSelect: (candidate: ScoredCandidate) => void;
  disabled: boolean;
}

export function CandidateRow({ candidate, onSelect, disabled }: CandidateRowProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <TableRow className="group">
        <TableCell className="font-bold text-center">
          <Badge variant={candidate.rank === 1 ? "default" : "outline"}>
            #{candidate.rank}
          </Badge>
        </TableCell>
        <TableCell>
          <div className="font-medium">{candidate.name}</div>
          <div className="text-xs text-muted-foreground">{candidate.employee_id}</div>
        </TableCell>
        <TableCell>
          <Badge className={licenseBadgeColor[candidate.license] ?? ""} variant="secondary">
            {candidate.license}
          </Badge>
        </TableCell>
        <TableCell className="text-xs">{candidate.employment_class.replace("_", " ")}</TableCell>
        <TableCell className="text-xs">{candidate.home_unit}</TableCell>
        <TableCell className="font-bold text-lg tabular-nums">
          {candidate.score.toFixed(2)}
        </TableCell>
        <TableCell>
          <ScoreBreakdown breakdown={candidate.score_breakdown} />
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => onSelect(candidate)} disabled={disabled}>
              Select
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Hide" : "Why?"}
            </Button>
          </div>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={8} className="bg-muted/30 text-sm italic">
            {candidate.rationale}
            <span className="ml-2 text-xs text-muted-foreground">
              ({candidate.rationale_source})
            </span>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}
