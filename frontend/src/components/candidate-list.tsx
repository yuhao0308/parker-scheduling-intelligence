"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Search, Users, X } from "lucide-react";
import {
  CandidateRow,
  type CandidateRowSubmitState,
} from "./candidate-row";
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
      <div className="collapsible-row" data-open={expanded}>
        <div>
          {expanded && <div className="space-y-2 pt-1">{children}</div>}
        </div>
      </div>
    </div>
  );
}

export function CandidateList({
  candidates,
  onSelect,
  disabled,
}: CandidateListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  // Per-row state machine for the "Contact" choreography.
  //   idle    — default
  //   sending — set on click; row gets the green sweep + spinner button
  //   sent    — set after the parent clears `disabled`; check icon + bg
  // Tracked here (not on the row) so an in-flight contact survives row
  // re-orders from filtering or weight tweaks.
  const [submitStates, setSubmitStates] = useState<
    Record<string, CandidateRowSubmitState>
  >({});
  const sendingId = useRef<string | null>(null);
  const wasDisabled = useRef(disabled);

  // When the parent's `disabled` flag flips back from true → false, the
  // mutation has resolved. Promote the `sending` row to `sent`.
  useEffect(() => {
    if (wasDisabled.current && !disabled && sendingId.current) {
      const id = sendingId.current;
      setSubmitStates((s) => ({ ...s, [id]: "sent" }));
      sendingId.current = null;
    }
    wasDisabled.current = disabled;
  }, [disabled]);

  function handleSelect(c: ScoredCandidate) {
    sendingId.current = c.employee_id;
    setSubmitStates((s) => ({ ...s, [c.employee_id]: "sending" }));
    onSelect(c);
  }

  if (candidates.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground">
        <Users className="h-6 w-6 motion-safe:animate-breathe" />
        <span>No staff available for this shift.</span>
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
          onSelect={handleSelect}
          disabled={disabled}
          submitStates={submitStates}
        />
      ) : (
        <TieredResults
          candidates={candidates}
          onSelect={handleSelect}
          disabled={disabled}
          submitStates={submitStates}
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
        aria-label="Search staff by name"
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
  submitStates,
}: {
  candidates: ScoredCandidate[];
  query: string;
  onSelect: (c: ScoredCandidate) => void;
  disabled: boolean;
  submitStates: Record<string, CandidateRowSubmitState>;
}) {
  const matches = useMemo(
    () => candidates.filter((c) => c.name.toLowerCase().includes(query)),
    [candidates, query],
  );

  if (matches.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted-foreground">
        <Users className="h-5 w-5 motion-safe:animate-breathe" />
        <span>No staff match &ldquo;{query}&rdquo;.</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {matches.length} match{matches.length === 1 ? "" : "es"}
      </p>
      {matches.map((c, i) => (
        <div
          key={c.employee_id}
          className="motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-safe:duration-300"
          style={{ animationDelay: `${Math.min(i * 40, 400)}ms` }}
        >
          <CandidateRow
            candidate={c}
            onSelect={onSelect}
            disabled={disabled}
            submitState={submitStates[c.employee_id] ?? "idle"}
          />
        </div>
      ))}
    </div>
  );
}

function TieredResults({
  candidates,
  onSelect,
  disabled,
  submitStates,
}: {
  candidates: ScoredCandidate[];
  onSelect: (c: ScoredCandidate) => void;
  disabled: boolean;
  submitStates: Record<string, CandidateRowSubmitState>;
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
      <div className="space-y-2 motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Best Match
        </p>
        <CandidateRow
          candidate={topRecommendation}
          onSelect={onSelect}
          disabled={disabled}
          isTop
          submitState={submitStates[topRecommendation.employee_id] ?? "idle"}
        />
      </div>

      {closeTierAlternatives.length > 0 && (
        <CollapsibleSection
          title="Nearly as Good"
          count={closeTierAlternatives.length}
        >
          {closeTierAlternatives.map((c) => (
            <CandidateRow
              key={c.employee_id}
              candidate={c}
              onSelect={onSelect}
              disabled={disabled}
              submitState={submitStates[c.employee_id] ?? "idle"}
            />
          ))}
        </CollapsibleSection>
      )}

      {strongAlternatives.length > 0 && (
        <CollapsibleSection
          title="Good Options"
          count={strongAlternatives.length}
        >
          {strongAlternatives.map((c) => (
            <CandidateRow
              key={c.employee_id}
              candidate={c}
              onSelect={onSelect}
              disabled={disabled}
              submitState={submitStates[c.employee_id] ?? "idle"}
            />
          ))}
        </CollapsibleSection>
      )}

      {backupOptions.length > 0 && (
        <CollapsibleSection title="If You Need More" count={backupOptions.length}>
          {backupOptions.map((c) => (
            <CandidateRow
              key={c.employee_id}
              candidate={c}
              onSelect={onSelect}
              disabled={disabled}
              submitState={submitStates[c.employee_id] ?? "idle"}
            />
          ))}
        </CollapsibleSection>
      )}
    </div>
  );
}
