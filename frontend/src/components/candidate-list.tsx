"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { CandidateRow } from "./candidate-row";
import { Input } from "@/components/ui/input";
import { tierCandidates } from "@/lib/tiering";
import type { ScoredCandidate } from "@/lib/types";

interface CandidateListProps {
  candidates: ScoredCandidate[];
  onSelect: (candidate: ScoredCandidate) => void;
  disabled: boolean;
}

function CollapsibleSection({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="mb-2 flex w-full items-center gap-2 py-1 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        <span>{title}</span>
        <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-xs">
          {count}
        </span>
      </button>
      {expanded && <div className="space-y-2">{children}</div>}
    </div>
  );
}

export function CandidateList({
  candidates,
  onSelect,
  disabled,
}: CandidateListProps) {
  const [searchQuery, setSearchQuery] = useState("");

  if (candidates.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        No eligible candidates found after filtering.
      </div>
    );
  }

  const trimmedQuery = searchQuery.trim().toLowerCase();

  return (
    <div className="space-y-4">
      <SearchBar
        value={searchQuery}
        onChange={setSearchQuery}
        onClear={() => setSearchQuery("")}
      />
      {trimmedQuery ? (
        <FilteredResults
          candidates={candidates}
          query={trimmedQuery}
          onSelect={onSelect}
          disabled={disabled}
        />
      ) : (
        <TieredResults
          candidates={candidates}
          onSelect={onSelect}
          disabled={disabled}
        />
      )}
    </div>
  );
}

function SearchBar({
  value,
  onChange,
  onClear,
}: {
  value: string;
  onChange: (v: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        type="search"
        role="searchbox"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search by name"
        aria-label="Search candidates by name"
        className="h-9 pl-9 pr-9 [&::-webkit-search-cancel-button]:appearance-none [&::-webkit-search-decoration]:appearance-none"
      />
      {value && (
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function FilteredResults({
  candidates,
  query,
  onSelect,
  disabled,
}: {
  candidates: ScoredCandidate[];
  query: string;
  onSelect: (c: ScoredCandidate) => void;
  disabled: boolean;
}) {
  const matches = useMemo(
    () => candidates.filter((c) => c.name.toLowerCase().includes(query)),
    [candidates, query],
  );

  if (matches.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No candidates match &ldquo;{query}&rdquo;.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {matches.length} match{matches.length === 1 ? "" : "es"}
      </p>
      {matches.map((c) => (
        <CandidateRow
          key={c.employee_id}
          candidate={c}
          onSelect={onSelect}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

function TieredResults({
  candidates,
  onSelect,
  disabled,
}: {
  candidates: ScoredCandidate[];
  onSelect: (c: ScoredCandidate) => void;
  disabled: boolean;
}) {
  const {
    topRecommendation,
    closeTierAlternatives,
    strongAlternatives,
    backupOptions,
  } = tierCandidates(candidates);

  return (
    <div className="space-y-5">
      {/* Top recommendation */}
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Top Recommendation
        </p>
        <CandidateRow
          candidate={topRecommendation}
          onSelect={onSelect}
          disabled={disabled}
          isTop
        />
      </div>

      {closeTierAlternatives.length > 0 && (
        <CollapsibleSection
          title="Very Close Alternatives"
          count={closeTierAlternatives.length}
        >
          {closeTierAlternatives.map((c) => (
            <CandidateRow
              key={c.employee_id}
              candidate={c}
              onSelect={onSelect}
              disabled={disabled}
            />
          ))}
        </CollapsibleSection>
      )}

      {strongAlternatives.length > 0 && (
        <CollapsibleSection
          title="Strong Alternatives"
          count={strongAlternatives.length}
        >
          {strongAlternatives.map((c) => (
            <CandidateRow
              key={c.employee_id}
              candidate={c}
              onSelect={onSelect}
              disabled={disabled}
            />
          ))}
        </CollapsibleSection>
      )}

      {backupOptions.length > 0 && (
        <CollapsibleSection title="Backup Options" count={backupOptions.length}>
          {backupOptions.map((c) => (
            <CandidateRow
              key={c.employee_id}
              candidate={c}
              onSelect={onSelect}
              disabled={disabled}
            />
          ))}
        </CollapsibleSection>
      )}
    </div>
  );
}
