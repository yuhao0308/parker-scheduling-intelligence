export type ShiftLabel = "DAY" | "EVENING" | "NIGHT";
export type LicenseType = "RN" | "LPN" | "CNA" | "PCT";
export type EmploymentClass = "FT" | "PT" | "PER_DIEM";

export interface ScoreBreakdown {
  overtime_headroom: number;
  proximity: number;
  clinical_fit: number;
  float_penalty: number;
  total: number;
}

// Client-facing typology labels. The DB enum is LT/SUBACUTE (clinical terms),
// but Parker staff say "Long-Term" / "Short-Term" — always render via this map.
export const TYPOLOGY_LABEL: Record<string, string> = {
  LT: "Long-Term",
  SUBACUTE: "Short-Term",
};

export function typologyLabel(value: string | null | undefined): string {
  if (!value) return "";
  return TYPOLOGY_LABEL[value] ?? value;
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
  recommendation_log_id: number;
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

export type ConfirmationStatus =
  | "UNSENT"
  | "PENDING"
  | "ACCEPTED"
  | "DECLINED"
  | "REPLACED";

export interface AssignedEmployee {
  employee_id: string;
  name: string;
  license: string;
  entry_id?: number;
  confirmation_status?: ConfirmationStatus;
}

export type ShiftSlotStatus =
  | "fully_staffed"
  | "partially_staffed"
  | "callout"
  | "unassigned";

export interface ShiftSlot {
  unit_id: string;
  unit_name: string;
  shift_date: string;
  shift_label: ShiftLabel;
  status: ShiftSlotStatus;
  assigned_employees: AssignedEmployee[];
  callout_count: number;
  callout_employee_ids: string[];
  required_count: number;
  unresolved_callout_count: number;
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

export interface WorkHoursSummary {
  employee_count: number;
  total_scheduled_hours: number;
  average_scheduled_hours: number;
  employees_near_ot: number;
  employees_in_ot: number;
  employees_high_ot: number;
  total_float_shifts: number;
}

export interface EmployeeWorkHours {
  employee_id: string;
  name: string;
  license: LicenseType;
  employment_class: EmploymentClass;
  home_unit_id: string | null;
  current_cycle_hours: number;
  current_cycle_shifts: number;
  scheduled_hours: number;
  scheduled_shifts: number;
  peak_week_hours: number;
  projected_overtime_hours: number;
  peak_biweekly_shifts: number;
  projected_overtime_shifts: number;
  double_shift_days: number;
  home_unit_shifts: number;
  float_shifts: number;
  callout_count: number;
  primary_unit_id: string | null;
  scheduled_unit_ids: string[];
  overtime_status: "healthy" | "near_ot" | "overtime" | "high_ot";
  overtime_detail: string;
}

export interface WorkHoursSnapshot {
  year: number;
  month: number;
  summary: WorkHoursSummary;
  employees: EmployeeWorkHours[];
}

export interface GenerateScheduleRequest {
  year: number;
  month: number;
  staff_count_override?: number;
  employee_pool?: string[];
}

export interface GenerateScheduleResult {
  entries_created: number;
  warnings: string[];
  scenario: string;
  unfilled_slots: number;
}

export interface RegenerateWeekRequest {
  week_start: string;
  employee_pool: string[];
  preserve_pending?: boolean;
}

export interface RegenerateWeekResult {
  week_start: string;
  entries_generated: number;
  slots_frozen: number;
  warnings: string[];
}

export interface AutogenSubmitRequest {
  week_start: string;
  employee_pool: string[];
  preserve_pending?: boolean;
}

export interface AutogenSubmitResult {
  week_start: string;
  entries_generated: number;
  entries_preserved: number;
  notifications_sent: number;
  unfilled_slots: number;
  warnings: string[];
}

export interface DemoConfig {
  demo_mode: boolean;
  confirmation_timeout_seconds: number;
  confirmation_timeout_label: string;
  outreach_timeout_seconds: number;
  outreach_timeout_label: string;
}

// --- Confirmation flow types ---

export interface StatusCounts {
  unsent: number;
  pending: number;
  accepted: number;
  declined: number;
  replaced: number;
}

export interface SendConfirmationsRequest {
  week_start: string;
  unit_ids?: string[];
}

export interface SendConfirmationsResult {
  week_start: string;
  entries_marked: number;
  notifications_created: number;
  counts_by_status: StatusCounts;
}

export interface ConfirmationEntry {
  entry_id: number;
  employee_id: string;
  name: string;
  license: string;
  unit_id: string;
  unit_name: string;
  shift_date: string;
  shift_label: ShiftLabel;
  confirmation_status: ConfirmationStatus;
  confirmation_sent_at: string | null;
  confirmation_responded_at: string | null;
  latest_notification_id: number | null;
}

export interface ConfirmationList {
  week_start: string;
  entries: ConfirmationEntry[];
  summary: StatusCounts;
}

export type ConfirmationResponse = "ACCEPTED" | "DECLINED" | "TIMEOUT";

export interface RespondConfirmationRequest {
  response: ConfirmationResponse;
}

export interface RespondConfirmationResult {
  entry_id: number;
  new_status: ConfirmationStatus;
  replacement: CalloutResponse | null;
}

export interface CommitDecision {
  entry_id: number;
  keep: boolean;
}

export interface CommitDecisionsRequest {
  week_start: string;
  employee_pool: string[];
  decisions: CommitDecision[];
}

export interface CommitDecisionsResult {
  week_start: string;
  accepted_count: number;
  declined_count: number;
  skipped_count: number;
  declined_employee_ids: string[];
  reroll_entries_generated: number;
  reroll_notifications_sent: number;
  unfilled_slots: number;
  warnings: string[];
  summary: StatusCounts;
}

export interface ReplaceEntryRequest {
  recommendation_log_id: number;
  selected_employee_id: string;
  selected_rank?: number;
}

export interface ReplaceEntryResult {
  old_entry_id: number;
  new_entry_id: number;
  new_status: ConfirmationStatus;
}

export interface RemoveEntryResult {
  entry_id: number;
  new_status: ConfirmationStatus;
  slot_now_open: boolean;
  canceled_notification_id: number | null;
}

export interface TimeoutSweepRequest {
  entry_ids: number[];
}

export interface TimeoutSweepResult {
  processed: number[];
  skipped: number[];
  processed_at: string;
}

// --- Outreach (last-minute callout) flow types ---

export type OutreachResponse = "ACCEPTED" | "DECLINED" | "TIMEOUT" | "SKIPPED";

export interface SendOutreachRequest {
  recommendation_log_id: number;
  candidate_employee_id: string;
  rank?: number;
}

export interface SendOutreachResult {
  notification_id: number;
  callout_id: number;
  employee_id: string;
  rank: number | null;
  status: string;
}

export interface RespondOutreachRequest {
  response: OutreachResponse;
  rank?: number;
  override_reason?: string;
}

export interface OutreachNotification {
  notification_id: number;
  employee_id: string;
  status: string;
  created_at: string;
  responded_at: string | null;
  rank: number | null;
  payload_text: string | null;
}

export interface RespondOutreachResult {
  notification_id: number;
  status: string;
  assigned_entry_id: number | null;
  canceled_notification_ids: number[];
  deprioritized_employee_ids: string[];
}

export interface CalloutDayCount {
  date: string;
  total: number;
  active: number;
}

export interface ScoringWeights {
  weights: {
    overtime_headroom: number;
    proximity: number;
    clinical_fit: number;
    float_penalty: number;
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
