"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScoreBreakdown } from "./score-breakdown";
import { cn } from "@/lib/utils";
import { ChevronDown, Send, Star } from "lucide-react";
import type { ScoredCandidate } from "@/lib/types";

const licenseBadgeClass: Record<string, string> = {
  RN: "bg-blue-100 text-blue-800 border-blue-200",
  LPN: "bg-green-100 text-green-800 border-green-200",
  CNA: "bg-amber-100 text-amber-800 border-amber-200",
  PCT: "bg-purple-100 text-purple-800 border-purple-200",
};

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-700";
  if (score >= 60) return "text-amber-700";
  return "text-slate-500";
}

interface CandidateRowProps {
  candidate: ScoredCandidate;
  onSelect: (candidate: ScoredCandidate) => void;
  disabled: boolean;
  isTop?: boolean;
}

export function CandidateRow({
  candidate,
  onSelect,
  disabled,
  isTop,
}: CandidateRowProps) {
  const [expanded, setExpanded] = useState(false);
  const scoreInt = Math.round(candidate.score * 100);

  return (
    <div
      className={cn(
        "rounded-lg border transition-colors",
        isTop
          ? "border-blue-200 bg-blue-50/40"
          : "bg-card hover:bg-muted/30",
      )}
    >
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Rank badge */}
        <div className="shrink-0">
          <span
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold",
              isTop
                ? "bg-blue-600 text-white"
                : "bg-muted text-muted-foreground",
            )}
          >
            {candidate.rank}
          </span>
        </div>

        {/* Name + meta */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold">{candidate.name}</span>
            <Badge
              variant="secondary"
              className={cn(
                "border text-[11px] px-1.5 py-0",
                licenseBadgeClass[candidate.license] ?? "",
              )}
            >
              {candidate.license}
            </Badge>
            {isTop && (
              <Badge className="gap-1 text-[11px] px-1.5 py-0 bg-blue-100 text-blue-800 border border-blue-200 font-semibold">
                <Star className="h-2.5 w-2.5 fill-current" />
                Best Match
              </Badge>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
            <span>{candidate.employment_class.replace(/_/g, " ")}</span>
            <span>·</span>
            <span>{candidate.home_unit}</span>
            <span>·</span>
            <span className="font-mono text-[10px]">{candidate.employee_id}</span>
          </div>
        </div>

        {/* Score breakdown bars (hidden on small screens) */}
        <div className="hidden lg:block shrink-0 w-44">
          <ScoreBreakdown breakdown={candidate.score_breakdown} />
        </div>

        {/* Numeric score */}
        <div className="shrink-0 text-right w-14">
          <span
            className={cn(
              "text-2xl font-bold tabular-nums leading-none",
              scoreColor(scoreInt),
            )}
          >
            {scoreInt}
          </span>
          <div className="text-[10px] text-muted-foreground leading-none mt-0.5">
            / 100
          </div>
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? "Hide why" : "Show why"}
          >
            <ChevronDown
              className={cn(
                "h-4 w-4 transition-transform duration-200",
                expanded && "rotate-180",
              )}
            />
          </Button>
          <Button
            size="sm"
            onClick={() => onSelect(candidate)}
            disabled={disabled}
            className="h-8 gap-1.5 px-3 text-xs"
          >
            <Send className="h-3 w-3" />
            Contact
          </Button>
        </div>
      </div>

      {/* Rationale panel */}
      {expanded && (
        <div className="border-t bg-muted/20 px-4 py-3">
          <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
            {candidate.rationale}
          </p>
        </div>
      )}
    </div>
  );
}
