import { describe, expect, it } from "vitest";

import { TIER1_MAX_GAP, TIER2_MAX_GAP, tierCandidates } from "./tiering";
import type { ScoredCandidate } from "./types";

function makeCandidate(rank: number, displayScore: number): ScoredCandidate {
  return {
    rank,
    employee_id: `E${rank}`,
    name: `Employee ${rank}`,
    license: "RN",
    employment_class: "FT",
    home_unit: "U1",
    score: displayScore / 100,
    score_breakdown: {
      overtime_headroom: 0,
      proximity: 0,
      clinical_fit: 0,
      float_penalty: 0,
      total: displayScore / 100,
    },
    rationale: { headline: "", highlights: [], reasons: [], risks: [] },
    rationale_source: "test",
    would_trigger_ot: false,
    ot_headroom_label: "",
    hours_this_cycle: 0,
    shift_count_this_biweek: 0,
    scheduled_shifts_this_month: 0,
    scheduled_hours_this_month: 0,
    peak_week_hours: 0,
    peak_biweekly_shifts: 0,
    projected_overtime_hours: 0,
    projected_overtime_shifts: 0,
    is_home_unit: false,
    home_unit_typology: null,
    target_unit_typology: null,
    clinical_fit_description: "",
    distance_miles: 0,
    tenure_years: null,
    days_since_last_shift: null,
    target_unit_shifts: 0,
    has_adjacent_shift: false,
  };
}

describe("tierCandidates", () => {
  it("throws on empty input", () => {
    expect(() => tierCandidates([])).toThrow(/empty/i);
  });

  it("returns three empty tier arrays for a single candidate", () => {
    const only = makeCandidate(1, 90);
    const result = tierCandidates([only]);
    expect(result.topRecommendation).toBe(only);
    expect(result.closeTierAlternatives).toEqual([]);
    expect(result.strongAlternatives).toEqual([]);
    expect(result.backupOptions).toEqual([]);
  });

  it("places a candidate with gap exactly 3 into closeTierAlternatives", () => {
    const top = makeCandidate(1, 90);
    const close = makeCandidate(2, 90 - TIER1_MAX_GAP); // gap == 3
    const result = tierCandidates([top, close]);
    expect(result.closeTierAlternatives).toEqual([close]);
    expect(result.strongAlternatives).toEqual([]);
    expect(result.backupOptions).toEqual([]);
  });

  it("places a candidate with gap exactly 4 into strongAlternatives", () => {
    const top = makeCandidate(1, 90);
    const strong = makeCandidate(2, 86); // gap == 4
    const result = tierCandidates([top, strong]);
    expect(result.closeTierAlternatives).toEqual([]);
    expect(result.strongAlternatives).toEqual([strong]);
    expect(result.backupOptions).toEqual([]);
  });

  it("places a candidate with gap exactly 8 into strongAlternatives (boundary)", () => {
    const top = makeCandidate(1, 90);
    const strong = makeCandidate(2, 90 - TIER2_MAX_GAP); // gap == 8
    const result = tierCandidates([top, strong]);
    expect(result.strongAlternatives).toEqual([strong]);
    expect(result.backupOptions).toEqual([]);
  });

  it("places a candidate with gap exactly 9 into backupOptions", () => {
    const top = makeCandidate(1, 90);
    const backup = makeCandidate(2, 81); // gap == 9
    const result = tierCandidates([top, backup]);
    expect(result.strongAlternatives).toEqual([]);
    expect(result.backupOptions).toEqual([backup]);
  });

  it("groups candidates with identical scores into closeTierAlternatives", () => {
    const candidates = [
      makeCandidate(1, 75),
      makeCandidate(2, 75),
      makeCandidate(3, 75),
      makeCandidate(4, 75),
    ];
    const result = tierCandidates(candidates);
    expect(result.topRecommendation).toBe(candidates[0]);
    expect(result.closeTierAlternatives).toEqual(candidates.slice(1));
    expect(result.strongAlternatives).toEqual([]);
    expect(result.backupOptions).toEqual([]);
  });

  it("splits a mixed list across all three tiers while preserving rank order", () => {
    const top = makeCandidate(1, 92);
    const close1 = makeCandidate(2, 91); // gap 1
    const close2 = makeCandidate(3, 89); // gap 3
    const strong1 = makeCandidate(4, 88); // gap 4
    const strong2 = makeCandidate(5, 84); // gap 8
    const backup1 = makeCandidate(6, 83); // gap 9
    const backup2 = makeCandidate(7, 70); // gap 22

    const result = tierCandidates([top, close1, close2, strong1, strong2, backup1, backup2]);

    expect(result.topRecommendation).toBe(top);
    expect(result.closeTierAlternatives).toEqual([close1, close2]);
    expect(result.strongAlternatives).toEqual([strong1, strong2]);
    expect(result.backupOptions).toEqual([backup1, backup2]);
  });
});
