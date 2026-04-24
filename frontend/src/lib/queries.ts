"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  autogenSubmit,
  commitDecisions,
  generateSchedule,
  getAllActiveStaff,
  getCallout,
  getDemoConfig,
  getMonthlySchedule,
  getRecentCallouts,
  getStaffForUnit,
  getUnits,
  getWeights,
  getWorkHoursSnapshot,
  listCalloutsByMonth,
  listConfirmations,
  listOutreach,
  regenerateWeek,
  removeEntry,
  resetCalendar,
  replaceEntry,
  respondConfirmation,
  respondOutreach,
  sendConfirmations,
  sendOutreach,
  submitCallout,
  submitOverride,
  timeoutSweep,
  updateWeights,
} from "./api";
import type {
  AutogenSubmitRequest,
  CalloutRequest,
  CommitDecisionsRequest,
  GenerateScheduleRequest,
  OverrideRequest,
  RegenerateWeekRequest,
  ReplaceEntryRequest,
  RespondConfirmationRequest,
  RespondOutreachRequest,
  ScoringWeights,
  SendConfirmationsRequest,
  SendOutreachRequest,
  TimeoutSweepRequest,
} from "./types";

export function useUnits() {
  return useQuery({
    queryKey: ["units"],
    queryFn: getUnits,
    staleTime: 5 * 60_000,
  });
}

export function useStaffForUnit(unitId: string | null) {
  return useQuery({
    queryKey: ["staff", unitId],
    queryFn: () => getStaffForUnit(unitId!),
    enabled: !!unitId,
  });
}

export function useAllActiveStaff() {
  return useQuery({
    queryKey: ["staff", "all"],
    queryFn: getAllActiveStaff,
    staleTime: 5 * 60_000,
  });
}

export function useSubmitCallout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CalloutRequest) => submitCallout(req),
    onSuccess: (data, req) => {
      // Seed the polling cache so consumers can render the initial
      // RUNNING state without a second network round-trip.
      qc.setQueryData(["callout", data.callout_id], data);
      const [year, month] = req.shift_date.split("-").map(Number);
      if (year && month) {
        qc.invalidateQueries({ queryKey: ["workHours", year, month] });
        qc.invalidateQueries({ queryKey: ["monthlySchedule", year, month] });
      }
    },
  });
}

export function useCalloutJob(calloutId: number | null) {
  return useQuery({
    queryKey: ["callout", calloutId],
    queryFn: () => getCallout(calloutId!),
    enabled: calloutId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1000;
      return data.status === "PENDING" || data.status === "RUNNING"
        ? 1000
        : false;
    },
  });
}

export function useSubmitOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: OverrideRequest) => submitOverride(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["recentCallouts"] });
    },
  });
}

export function useRecentCallouts(limit = 20) {
  return useQuery({
    queryKey: ["recentCallouts", limit],
    queryFn: () => getRecentCallouts(limit),
  });
}

export function useWeights() {
  return useQuery({
    queryKey: ["weights"],
    queryFn: getWeights,
  });
}

export function useUpdateWeights() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<ScoringWeights>) => updateWeights(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["weights"] });
      qc.invalidateQueries({ queryKey: ["workHours"] });
    },
  });
}

export function useResetCalendar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: resetCalendar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
      qc.invalidateQueries({ queryKey: ["workHours"] });
      qc.invalidateQueries({ queryKey: ["confirmations"] });
      qc.invalidateQueries({ queryKey: ["recentCallouts"] });
      qc.invalidateQueries({ queryKey: ["outreach"] });
      qc.invalidateQueries({ queryKey: ["calloutsByMonth"] });
    },
  });
}

export function useMonthlySchedule(year: number, month: number) {
  return useQuery({
    queryKey: ["monthlySchedule", year, month],
    queryFn: () => getMonthlySchedule(year, month),
    staleTime: 30_000,
  });
}

export function useWorkHoursSnapshot(
  year: number,
  month: number,
  enabled = true,
) {
  return useQuery({
    queryKey: ["workHours", year, month],
    queryFn: () => getWorkHoursSnapshot(year, month),
    staleTime: 15_000,
    enabled,
    refetchInterval: enabled ? 15_000 : false,
  });
}

export function useGenerateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: GenerateScheduleRequest) => generateSchedule(req),
    onSuccess: (_, req) => {
      qc.invalidateQueries({ queryKey: ["monthlySchedule", req.year, req.month] });
      qc.invalidateQueries({ queryKey: ["workHours", req.year, req.month] });
    },
  });
}

// --- Confirmation flow ---

export function useConfirmations(weekStart: string, enabled = true) {
  return useQuery({
    queryKey: ["confirmations", weekStart],
    queryFn: () => listConfirmations(weekStart),
    enabled,
    staleTime: 5_000,
  });
}

export function useSendConfirmations() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: SendConfirmationsRequest) => sendConfirmations(req),
    onSuccess: (_, req) => {
      qc.invalidateQueries({ queryKey: ["confirmations", req.week_start] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

export function useRespondConfirmation(weekStart: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { entryId: number; req: RespondConfirmationRequest }) =>
      respondConfirmation(args.entryId, args.req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["confirmations", weekStart] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

export function useCommitDecisions(weekStart: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CommitDecisionsRequest) => commitDecisions(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["confirmations", weekStart] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

export function useReplaceEntry(weekStart: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { entryId: number; req: ReplaceEntryRequest }) =>
      replaceEntry(args.entryId, args.req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["confirmations", weekStart] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

export function useRemoveEntry(weekStart: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entryId: number) => removeEntry(entryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["confirmations", weekStart] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

export function useTimeoutSweep(weekStart: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: TimeoutSweepRequest) => timeoutSweep(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["confirmations", weekStart] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

export function useRegenerateWeek() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: RegenerateWeekRequest) => regenerateWeek(req),
    onSuccess: (_, req) => {
      qc.invalidateQueries({ queryKey: ["confirmations", req.week_start] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

export function useAutogenSubmit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: AutogenSubmitRequest) => autogenSubmit(req),
    onSuccess: (_, req) => {
      qc.invalidateQueries({ queryKey: ["confirmations", req.week_start] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}

// Demo / system config — cached for a long time; rarely changes.
export function useDemoConfig() {
  return useQuery({
    queryKey: ["demoConfig"],
    queryFn: getDemoConfig,
    staleTime: 60 * 60_000,
  });
}

// Per-day callout rollup feeding calendar red-dot indicators + mini calendar.
export function useCalloutsByMonth(month: string, enabled = true) {
  return useQuery({
    queryKey: ["calloutsByMonth", month],
    queryFn: () => listCalloutsByMonth(month),
    enabled,
    staleTime: 30_000,
  });
}

// --- Outreach (last-minute callout) flow ---

export function useOutreach(calloutId: number | null) {
  return useQuery({
    queryKey: ["outreach", calloutId],
    queryFn: () => listOutreach(calloutId!),
    enabled: !!calloutId,
    staleTime: 5_000,
  });
}

export function useSendOutreach() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { calloutId: number; req: SendOutreachRequest }) =>
      sendOutreach(args.calloutId, args.req),
    onSuccess: (_, args) => {
      qc.invalidateQueries({ queryKey: ["outreach", args.calloutId] });
    },
  });
}

export function useRespondOutreach() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      calloutId: number;
      notificationId: number;
      req: RespondOutreachRequest;
    }) => respondOutreach(args.calloutId, args.notificationId, args.req),
    onSuccess: (_, args) => {
      qc.invalidateQueries({ queryKey: ["outreach", args.calloutId] });
      qc.invalidateQueries({ queryKey: ["monthlySchedule"] });
    },
  });
}
