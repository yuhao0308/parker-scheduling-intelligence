"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  generateSchedule,
  getMonthlySchedule,
  getRecentCallouts,
  getStaffForUnit,
  getUnits,
  getWeights,
  getWorkHoursSnapshot,
  submitCallout,
  submitOverride,
  updateWeights,
} from "./api";
import type {
  CalloutRequest,
  GenerateScheduleRequest,
  OverrideRequest,
  ScoringWeights,
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

export function useSubmitCallout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CalloutRequest) => submitCallout(req),
    onSuccess: (_, req) => {
      const [year, month] = req.shift_date.split("-").map(Number);
      if (year && month) {
        qc.invalidateQueries({ queryKey: ["workHours", year, month] });
        qc.invalidateQueries({ queryKey: ["monthlySchedule", year, month] });
      }
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
