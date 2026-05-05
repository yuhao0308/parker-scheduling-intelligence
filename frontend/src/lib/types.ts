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
// but United Hebrew staff say "Long-Term" / "Short-Term" — always render via this map.
export const TYPOLOGY_LABEL: Record<string, string> = {
  LT: "Long-Term",
  SUBACUTE: "Short-Term",
};

export function typologyLabel(value: string | null | undefined): string {
  if (!value) return "";
  return TYPOLOGY_LABEL[value] ?? value;
}

export type RationaleTone = "positive" | "neutral" | "warning" | "danger";

export interface RationaleHighlight {
  label: string;
  value: string;
  tone: RationaleTone;
}

export interface Rationale {
  headline: string;
  highlights: RationaleHighlight[];
  reasons: string[];
  risks: string[];
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
  rationale: Rationale;
  rationale_source: string;
  would_trigger_ot: boolean;
  ot_headroom_label: string;
  hours_this_cycle: number;
  shift_count_this_biweek: number;
  scheduled_shifts_this_month: number;
  scheduled_hours_this_month: number;
  peak_week_hours: number;
  peak_biweekly_shifts: number;
  projected_overtime_hours: number;
  projected_overtime_shifts: number;
  is_home_unit: boolean;
  home_unit_typology: string | null;
  target_unit_typology: string | null;
  clinical_fit_description: string;
  distance_miles: number;
  tenure_years: number | null;
  days_since_last_shift: number | null;
  target_unit_shifts: number;
  has_adjacent_shift: boolean;
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

export interface CalledOutEmployee {
  employee_id: string;
  name: string;
  license: LicenseType;
  employment_class: EmploymentClass;
  home_unit_id: string | null;
  home_unit_name: string | null;
  hire_date: string | null;
}

export interface CalloutResponse {
  callout_id: number;
  recommendation_log_id: number;
  unit_id: string;
  unit_name: string;
  shift_date: string;
  shift_label: ShiftLabel;
  called_out_employee: CalledOutEmployee;
  candidates: ScoredCandidate[];
  filter_stats: FilterStats;
  generated_at: string;
}

export type CalloutJobStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface CalloutJobResponse {
  callout_id: number;
  status: CalloutJobStatus;
  unit_id: string;
  unit_name: string;
  shift_date: string;
  shift_label: ShiftLabel;
  called_out_employee: CalledOutEmployee;
  reported_at: string;
  error_message: string | null;
  recommendation_log_id: number | null;
  candidates: ScoredCandidate[] | null;
  filter_stats: FilterStats | null;
  generated_at: string | null;
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
  employee_name: string | null;
  employee_license: LicenseType | null;
  unit_id: string;
  unit_name: string | null;
  shift_date: string;
  shift_label: string;
  reason: string | null;
  reported_at: string;
  recommendation_id: number | null;
  ranked_candidates: ScoredCandidate[] | null;
  filter_stats: FilterStats | null;
  override_id: number | null;
  selected_employee_id: string | null;
  selected_employee_name: string | null;
  selected_employee_license: LicenseType | null;
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

export type CalendarLoadingScope =
  | { kind: "month"; year: number; month: number; label: string }
  | { kind: "week"; weekStart: string; label: string };

export interface WorkHoursSummary {
  employee_count: number;
  total_scheduled_hours: number;
  average_scheduled_hours: number;
  employees_near_ot: number;
  employees_in_ot: number;
  employees_high_ot: number;
  total_float_shifts: number;
  // Counts derived from role-specific OT periods, not the calendar month.
  // Daily OT is RN-specific; biweekly OT follows RN shift limits and non-RN budgets.
  daily_ot_count?: number;
  biweekly_ot_count?: number;
}

export interface WorkloadPeriod {
  period_type: "week" | "biweekly" | string;
  start_date: string;
  end_date: string;
  worked_hours: number;
  worked_shifts: number;
  scheduled_hours: number;
  scheduled_shifts: number;
  projected_hours: number;
  projected_shifts: number;
  threshold_hours: number;
  remaining_hours: number;
  overtime_hours: number;
  double_shift_days: number;
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
  worked_hours_this_month?: number;
  worked_shifts_this_month?: number;
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
  // Biweekly cycle metrics for the three-segment workload bar. All optional
  // so the UI degrades gracefully if the backend hasn't been redeployed.
  worked_hours_this_cycle?: number;
  scheduled_hours_this_cycle?: number;
  budget_hours_this_cycle?: number;
  cycle_start_date?: string | null;
  cycle_end_date?: string | null;
  weekly_periods?: WorkloadPeriod[];
  biweekly_periods?: WorkloadPeriod[];
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

export interface MonthlyAutogenSubmitRequest {
  year: number;
  month: number;
  employee_pool: string[];
  /** ISO date (YYYY-MM-DD). When provided with period_end, autogen runs over
   *  the inclusive 28-day rotation instead of the calendar month. */
  period_start?: string;
  /** ISO date (YYYY-MM-DD). Inclusive end of the 4-week period. */
  period_end?: string;
}

export interface MonthlyAutogenSubmitResult {
  year: number;
  month: number;
  entries_generated: number;
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

export interface CommitMonthlyDecisionsRequest {
  year: number;
  month: number;
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
  ot_warning_thresholds?: {
    standard_hours_remaining_amber: number;
    rn_shifts_remaining_amber: number;
  };
}
