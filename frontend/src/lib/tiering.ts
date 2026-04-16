import type { ScoredCandidate } from "@/lib/types";

// Tier thresholds in display-score points (0-100 scale).
// Adjust these constants to change tier boundaries.
export const TIER1_MAX_GAP = 3;
export const TIER2_MAX_GAP = 8;

export interface TieredCandidates {
  /** Rank-1 candidate, always shown prominently. */
  topRecommendation: ScoredCandidate;
  /** Other Tier 1 candidates (display-score gap <= TIER1_MAX_GAP). */
  closeTierAlternatives: ScoredCandidate[];
  /** Tier 2 candidates (TIER1_MAX_GAP < gap <= TIER2_MAX_GAP). */
  strongAlternatives: ScoredCandidate[];
  /** Tier 3 candidates (gap > TIER2_MAX_GAP). */
  backupOptions: ScoredCandidate[];
}

/**
 * Assign presentation tiers based on display-score distance from the top candidate.
 *
 * Tiering is purely presentational: the input ordering (rank from the backend) is
 * preserved within each tier. The underlying ranking algorithm and raw scores are
 * not modified in any way.
 */
export function tierCandidates(candidates: ScoredCandidate[]): TieredCandidates {
  if (candidates.length === 0) {
    throw new Error("tierCandidates: cannot tier an empty candidate list");
  }

  const [top, ...rest] = candidates;
  const topDisplayScore = Math.round(top.score * 100);

  const closeTierAlternatives: ScoredCandidate[] = [];
  const strongAlternatives: ScoredCandidate[] = [];
  const backupOptions: ScoredCandidate[] = [];

  for (const candidate of rest) {
    const gap = topDisplayScore - Math.round(candidate.score * 100);
    if (gap <= TIER1_MAX_GAP) {
      closeTierAlternatives.push(candidate);
    } else if (gap <= TIER2_MAX_GAP) {
      strongAlternatives.push(candidate);
    } else {
      backupOptions.push(candidate);
    }
  }

  return {
    topRecommendation: top,
    closeTierAlternatives,
    strongAlternatives,
    backupOptions,
  };
}
