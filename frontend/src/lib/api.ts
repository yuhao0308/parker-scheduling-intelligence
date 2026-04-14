import type {
  CalloutRequest,
  CalloutResponse,
  GenerateScheduleRequest,
  GenerateScheduleResult,
  MonthlySchedule,
  OverrideRequest,
  OverrideResponse,
  RecentCallout,
  ScoringWeights,
  StaffOut,
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

export const submitCallout = (req: CalloutRequest) =>
  post<CalloutResponse>("/callouts", req);

export const submitOverride = (req: OverrideRequest) =>
  post<OverrideResponse>("/overrides", req);

export const getRecentCallouts = (limit = 20) =>
  request<RecentCallout[]>(`/callouts/recent?limit=${limit}`);

export const getWeights = () => request<ScoringWeights>("/config/weights");

export const updateWeights = (payload: Partial<ScoringWeights>) =>
  put<ScoringWeights>("/config/weights", payload);

export const getMonthlySchedule = (year: number, month: number) =>
  request<MonthlySchedule>(`/schedule/monthly?year=${year}&month=${month}`);

export const getWorkHoursSnapshot = (year: number, month: number) =>
  request<WorkHoursSnapshot>(`/schedule/work-hours?year=${year}&month=${month}`);

export const generateSchedule = (req: GenerateScheduleRequest) =>
  post<GenerateScheduleResult>("/schedule/generate", req);
