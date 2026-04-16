"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CandidateRow } from "./candidate-row";
import { tierCandidates } from "@/lib/tiering";
import type { ScoredCandidate } from "@/lib/types";

interface CandidateListProps {
  candidates: ScoredCandidate[];
  onSelect: (candidate: ScoredCandidate) => void;
  disabled: boolean;
}

function CandidateTableHeader() {
  return (
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
  );
}

interface CollapsibleSectionProps {
  title: string;
  count: number;
  children: React.ReactNode;
}

function CollapsibleSection({ title, count, children }: CollapsibleSectionProps) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="border rounded-md">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-left hover:bg-muted/50"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <span>
          {title} ({count})
        </span>
      </button>
      {expanded && <div className="border-t">{children}</div>}
    </div>
  );
}

export function CandidateList({ candidates, onSelect, disabled }: CandidateListProps) {
  if (candidates.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No eligible candidates found after filtering.
      </div>
    );
  }

  const { topRecommendation, closeTierAlternatives, strongAlternatives, backupOptions } =
    tierCandidates(candidates);

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Candidates are grouped by similarity to the top recommendation. All scores,
        rationale, and breakdowns remain accessible.
      </p>

      <div className="space-y-2">
        <div className="text-sm font-semibold">Top Recommendation</div>
        <Table>
          <CandidateTableHeader />
          <TableBody>
            <CandidateRow
              key={topRecommendation.employee_id}
              candidate={topRecommendation}
              onSelect={onSelect}
              disabled={disabled}
            />
          </TableBody>
        </Table>
      </div>

      {closeTierAlternatives.length > 0 && (
        <CollapsibleSection
          title="Very Close Alternatives"
          count={closeTierAlternatives.length}
        >
          <Table>
            <CandidateTableHeader />
            <TableBody>
              {closeTierAlternatives.map((candidate) => (
                <CandidateRow
                  key={candidate.employee_id}
                  candidate={candidate}
                  onSelect={onSelect}
                  disabled={disabled}
                />
              ))}
            </TableBody>
          </Table>
        </CollapsibleSection>
      )}

      {strongAlternatives.length > 0 && (
        <CollapsibleSection title="Strong Alternatives" count={strongAlternatives.length}>
          <Table>
            <CandidateTableHeader />
            <TableBody>
              {strongAlternatives.map((candidate) => (
                <CandidateRow
                  key={candidate.employee_id}
                  candidate={candidate}
                  onSelect={onSelect}
                  disabled={disabled}
                />
              ))}
            </TableBody>
          </Table>
        </CollapsibleSection>
      )}

      {backupOptions.length > 0 && (
        <CollapsibleSection title="Backup Options" count={backupOptions.length}>
          <Table>
            <CandidateTableHeader />
            <TableBody>
              {backupOptions.map((candidate) => (
                <CandidateRow
                  key={candidate.employee_id}
                  candidate={candidate}
                  onSelect={onSelect}
                  disabled={disabled}
                />
              ))}
            </TableBody>
          </Table>
        </CollapsibleSection>
      )}
    </div>
  );
}
