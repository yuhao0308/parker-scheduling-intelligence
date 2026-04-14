export type ShiftLabel = "DAY" | "EVENING" | "NIGHT";
export type LicenseType = "RN" | "LPN" | "CNA" | "PCT";
export type EmploymentClass = "FT" | "PT" | "PER_DIEM";

export interface ScoreBreakdown {
  overtime_headroom: number;
  proximity: number;
  clinical_fit: number;
  float_penalty: number;
  historical_acceptance: number;
  total: number;
}

export interface ScoredCandidate {
  rank: number;
  employee_id: string;
  name: string;
  license: LicenseType;
  employment_class: EmploymentClass;
  home_unit: string;
  score: number;
  score_breakdown: ScoreBreakdown;
  rationale: string;
  rationale_source: string;
}

export interface FilterStats {
  total_pool: number;
  passed_filter: number;
  filtered_out: Record<string, number>;
}

export interface CalloutRequest {
  callout_employee_id: string;
  unit_id: string;
  shift_date: string;
  shift_label: ShiftLabel;
}

export interface CalloutResponse {
  callout_id: number;
  unit_id: string;
  unit_name: string;
  shift_date: string;
  shift_label: ShiftLabel;
  candidates: ScoredCandidate[];
  filter_stats: FilterStats;
  generated_at: string;
}

export interface OverrideRequest {
  recommendation_log_id: number;
  selected_employee_id: string;
  coordinator_id: string;
  override_reason?: string;
}

export interface OverrideResponse {
  override_id: number;
  recommendation_log_id: number;
  selected_employee_id: string;
  selected_rank: number | null;
}

export interface UnitOut {
  unit_id: string;
  name: string;
  typology: string;
}

export interface StaffOut {
  employee_id: string;
  name: string;
  license: string;
  employment_class: string;
  home_unit_id: string | null;
}

export interface RecentCallout {
  callout_id: number;
  employee_id: string;
  unit_id: string;
  shift_date: string;
  shift_label: string;
  reason: string | null;
  reported_at: string;
  recommendation_id: number | null;
  ranked_candidates: ScoredCandidate[] | null;
  filter_stats: FilterStats | null;
  override_id: number | null;
  selected_employee_id: string | null;
  selected_rank: number | null;
  override_reason: string | null;
}

// --- Monthly schedule types ---

export interface AssignedEmployee {
  employee_id: string;
  name: string;
  license: string;
}

export interface ShiftSlot {
  unit_id: string;
  unit_name: string;
  shift_date: string;
  shift_label: ShiftLabel;
  status: "assigned" | "unassigned" | "callout";
  assigned_employees: AssignedEmployee[];
  callout_count: number;
  callout_employee_ids: string[];
}

export interface DaySchedule {
  date: string;
  slots: ShiftSlot[];
}

export interface MonthlySchedule {
  year: number;
  month: number;
  days: DaySchedule[];
}

export interface GenerateScheduleRequest {
  year: number;
  month: number;
  staff_count_override?: number;
}

export interface GenerateScheduleResult {
  entries_created: number;
  warnings: string[];
  scenario: string;
  unfilled_slots: number;
}

export interface ScoringWeights {
  weights: {
    overtime_headroom: number;
    proximity: number;
    clinical_fit: number;
    float_penalty: number;
    historical_acceptance: number;
  };
  thresholds: {
    max_relevant_distance_miles: number;
    max_candidates_returned: number;
    new_hire_months: number;
  };
  clinical_fit_scores: {
    exact_match: number;
    subacute_to_lt: number;
    lt_to_subacute: number;
  };
  float_penalty_values: {
    home_unit: number;
    same_typology: number;
    cross_typology: number;
    new_hire_multiplier: number;
  };
}
