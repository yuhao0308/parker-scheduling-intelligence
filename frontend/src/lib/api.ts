import type {
  AutogenSubmitRequest,
  AutogenSubmitResult,
  CalloutDayCount,
  CalloutRequest,
  CalloutResponse,
  CommitDecisionsRequest,
  CommitDecisionsResult,
  ConfirmationList,
  DemoConfig,
  GenerateScheduleRequest,
  GenerateScheduleResult,
  MonthlySchedule,
  OutreachNotification,
  OverrideRequest,
  OverrideResponse,
  RecentCallout,
  RegenerateWeekRequest,
  RegenerateWeekResult,
  RemoveEntryResult,
  ReplaceEntryRequest,
  ReplaceEntryResult,
  RespondConfirmationRequest,
  RespondConfirmationResult,
  RespondOutreachRequest,
  RespondOutreachResult,
  ScoringWeights,
  SendConfirmationsRequest,
  SendConfirmationsResult,
  SendOutreachRequest,
  SendOutreachResult,
  StaffOut,
  TimeoutSweepRequest,
  TimeoutSweepResult,
  UnitOut,
  WorkHoursSnapshot,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function put<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const getUnits = () => request<UnitOut[]>("/units");

export const getStaffForUnit = (unitId: string) =>
  request<StaffOut[]>(`/units/${unitId}/staff`);

export const getAllActiveStaff = () => request<StaffOut[]>("/staff");

export const submitCallout = (req: CalloutRequest) =>
  post<CalloutResponse>("/callouts", req);

export const submitOverride = (req: OverrideRequest) =>
  post<OverrideResponse>("/overrides", req);

export const getRecentCallouts = (limit = 20) =>
  request<RecentCallout[]>(`/callouts/recent?limit=${limit}`);

export const getWeights = () => request<ScoringWeights>("/config/weights");

export const updateWeights = (payload: Partial<ScoringWeights>) =>
  put<ScoringWeights>("/config/weights", payload);

export const resetCalendar = () =>
  post<{ entries_deleted: number }>("/config/reset-calendar", {});

export const getMonthlySchedule = (year: number, month: number) =>
  request<MonthlySchedule>(`/schedule/monthly?year=${year}&month=${month}`);

export const getWorkHoursSnapshot = (year: number, month: number) =>
  request<WorkHoursSnapshot>(`/schedule/work-hours?year=${year}&month=${month}`);

export const generateSchedule = (req: GenerateScheduleRequest) =>
  post<GenerateScheduleResult>("/schedule/generate", req);

export const regenerateWeek = (req: RegenerateWeekRequest) =>
  post<RegenerateWeekResult>("/schedule/regenerate-week", req);

export const autogenSubmit = (req: AutogenSubmitRequest) =>
  post<AutogenSubmitResult>("/schedule/autogen-submit", req);

// Demo / system config
export const getDemoConfig = () => request<DemoConfig>("/config/demo");

// Callout day-level rollup (for calendar red dots + mini calendar)
export const listCalloutsByMonth = (month: string) =>
  request<CalloutDayCount[]>(`/callouts?month=${encodeURIComponent(month)}`);

// Confirmation flow
export const sendConfirmations = (req: SendConfirmationsRequest) =>
  post<SendConfirmationsResult>("/schedule/confirmations/send", req);

export const listConfirmations = (weekStart: string, unitIds?: string[]) => {
  const params = new URLSearchParams({ week_start: weekStart });
  if (unitIds?.length) {
    for (const id of unitIds) params.append("unit_ids", id);
  }
  return request<ConfirmationList>(`/schedule/confirmations?${params.toString()}`);
};

export const respondConfirmation = (
  entryId: number,
  req: RespondConfirmationRequest,
) =>
  post<RespondConfirmationResult>(
    `/schedule/confirmations/${entryId}/respond`,
    req,
  );

export const commitDecisions = (req: CommitDecisionsRequest) =>
  post<CommitDecisionsResult>("/schedule/confirmations/commit", req);

export const replaceEntry = (entryId: number, req: ReplaceEntryRequest) =>
  post<ReplaceEntryResult>(`/schedule/confirmations/${entryId}/replace`, req);

export const removeEntry = (entryId: number) =>
  post<RemoveEntryResult>(`/schedule/confirmations/${entryId}/remove`, {});

export const timeoutSweep = (req: TimeoutSweepRequest) =>
  post<TimeoutSweepResult>("/schedule/confirmations/timeout-sweep", req);

// Callout outreach flow
export const sendOutreach = (calloutId: number, req: SendOutreachRequest) =>
  post<SendOutreachResult>(`/callouts/${calloutId}/outreach/next`, req);

export const respondOutreach = (
  calloutId: number,
  notificationId: number,
  req: RespondOutreachRequest,
) =>
  post<RespondOutreachResult>(
    `/callouts/${calloutId}/outreach/${notificationId}/respond`,
    req,
  );

export const listOutreach = (calloutId: number) =>
  request<OutreachNotification[]>(`/callouts/${calloutId}/outreach`);
