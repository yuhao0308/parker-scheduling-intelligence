// =============================================================================
// DEMO ONLY — emulates HR integration for PTO / Leave Requests.
//
// In production this should be replaced with a real PTO accrual API and HR
// system sync. This module persists requests in localStorage so the demo flow
// survives page reloads, and exposes a tiny pub/sub for React components.
// =============================================================================

"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "parker:demo:pto-requests";
const SEEDED_FLAG_KEY = "parker:demo:pto-seeded";

export type PtoRequestType =
  | "PTO"
  | "Sick"
  | "Vacation"
  | "Holiday"
  | "Planned Sick Leave"
  | "Other";

export type PtoRequestStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface PtoRequest {
  id: string;
  employee_id: string;
  employee_name: string;
  license: string;
  home_unit_id: string | null;
  request_type: PtoRequestType;
  start_date: string; // YYYY-MM-DD
  end_date: string; // YYYY-MM-DD
  total_hours: number;
  sick_balance: number;
  pto_balance: number;
  status: PtoRequestStatus;
  decided_at?: string;
  // Filled in on approval — pointer to the affected shift that became a callout.
  affected_shift?: {
    shift_date: string;
    shift_label: "DAY" | "EVENING" | "NIGHT";
    unit_id: string;
    hours_used: number;
    sick_used: number;
    pto_used: number;
  };
  // Once the callout is created, store its id so the UI can deep-link.
  callout_id?: number;
}

// ---------------------------------------------------------------------------
// In-memory store + subscribers (for cross-component reactivity).
// ---------------------------------------------------------------------------

let _cache: PtoRequest[] | null = null;
const subscribers = new Set<() => void>();

function readStorage(): PtoRequest[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PtoRequest[]) : [];
  } catch {
    return [];
  }
}

function writeStorage(list: PtoRequest[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // Ignore quota / privacy-mode errors.
  }
}

function notify() {
  for (const sub of subscribers) sub();
}

function ensureCache(): PtoRequest[] {
  if (_cache === null) {
    _cache = readStorage();
  }
  return _cache;
}

export function getPtoRequests(): PtoRequest[] {
  return ensureCache();
}

export function addPtoRequest(req: Omit<PtoRequest, "id" | "status">): PtoRequest {
  const list = ensureCache();
  const created: PtoRequest = {
    ...req,
    id: `pto_${Date.now()}_${Math.floor(Math.random() * 1e6)}`,
    status: "PENDING",
  };
  _cache = [created, ...list];
  writeStorage(_cache);
  notify();
  return created;
}

export function updatePtoRequest(id: string, patch: Partial<PtoRequest>) {
  const list = ensureCache();
  const next = list.map((r) => (r.id === id ? { ...r, ...patch } : r));
  _cache = next;
  writeStorage(_cache);
  notify();
}

export function setPtoStatus(id: string, status: PtoRequestStatus) {
  updatePtoRequest(id, { status, decided_at: new Date().toISOString() });
}

export function clearAllPtoRequests() {
  _cache = [];
  writeStorage(_cache);
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(SEEDED_FLAG_KEY);
  }
  notify();
}

// ---------------------------------------------------------------------------
// Seed data — fired once per browser so the demo always has content.
// Picks employees from a provided staff list so the IDs match real records.
// ---------------------------------------------------------------------------

interface SeedStaff {
  employee_id: string;
  name: string;
  license: string;
  home_unit_id: string | null;
}

export function seedDemoPtoRequestsIfNeeded(staff: SeedStaff[]) {
  if (typeof window === "undefined") return;
  if (window.localStorage.getItem(SEEDED_FLAG_KEY) === "1") return;
  if (staff.length === 0) return;

  // Pick a few representative people across licenses.
  const pickByLicense = (lic: string) =>
    staff.find((s) => s.license === lic) ?? staff[0];

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const isoDate = (d: Date) => d.toISOString().slice(0, 10);

  const inDays = (n: number) => {
    const d = new Date(today);
    d.setDate(d.getDate() + n);
    return d;
  };

  const seeds: Omit<PtoRequest, "id" | "status">[] = [];

  const rn = pickByLicense("RN");
  if (rn) {
    seeds.push({
      employee_id: rn.employee_id,
      employee_name: rn.name,
      license: rn.license,
      home_unit_id: rn.home_unit_id,
      request_type: "PTO",
      start_date: isoDate(inDays(2)),
      end_date: isoDate(inDays(4)),
      total_hours: 24,
      sick_balance: 16,
      pto_balance: 88,
    });
  }

  const lpn = pickByLicense("LPN");
  if (lpn && lpn.employee_id !== rn?.employee_id) {
    seeds.push({
      employee_id: lpn.employee_id,
      employee_name: lpn.name,
      license: lpn.license,
      home_unit_id: lpn.home_unit_id,
      request_type: "Planned Sick Leave",
      start_date: isoDate(inDays(7)),
      end_date: isoDate(inDays(7)),
      total_hours: 8,
      sick_balance: 42,
      pto_balance: 60,
    });
  }

  const cna = pickByLicense("CNA");
  if (
    cna &&
    cna.employee_id !== rn?.employee_id &&
    cna.employee_id !== lpn?.employee_id
  ) {
    seeds.push({
      employee_id: cna.employee_id,
      employee_name: cna.name,
      license: cna.license,
      home_unit_id: cna.home_unit_id,
      request_type: "Vacation",
      start_date: isoDate(inDays(10)),
      end_date: isoDate(inDays(14)),
      total_hours: 40,
      sick_balance: 8,
      pto_balance: 120,
    });
  }

  const fourth = staff.find(
    (s) =>
      s.employee_id !== rn?.employee_id &&
      s.employee_id !== lpn?.employee_id &&
      s.employee_id !== cna?.employee_id,
  );
  if (fourth) {
    seeds.push({
      employee_id: fourth.employee_id,
      employee_name: fourth.name,
      license: fourth.license,
      home_unit_id: fourth.home_unit_id,
      request_type: "Holiday",
      start_date: isoDate(inDays(20)),
      end_date: isoDate(inDays(20)),
      total_hours: 8,
      sick_balance: 0,
      pto_balance: 32,
    });
  }

  const list = ensureCache();
  const existingIds = new Set(list.map((r) => r.id));
  for (const seed of seeds) {
    const created: PtoRequest = {
      ...seed,
      id: `pto_seed_${seed.employee_id}_${seed.start_date}`,
      status: "PENDING",
    };
    if (!existingIds.has(created.id)) {
      list.unshift(created);
    }
  }
  _cache = list;
  writeStorage(_cache);
  window.localStorage.setItem(SEEDED_FLAG_KEY, "1");
  notify();
}

// ---------------------------------------------------------------------------
// React hook — subscribes to mutations.
// ---------------------------------------------------------------------------

export function useDemoPtoRequests(): PtoRequest[] {
  const [snapshot, setSnapshot] = useState<PtoRequest[]>(() => getPtoRequests());

  useEffect(() => {
    const tick = () => setSnapshot(getPtoRequests().slice());
    subscribers.add(tick);
    // Sync from any writes that happened in another tab.
    tick();
    return () => {
      subscribers.delete(tick);
    };
  }, []);

  return snapshot;
}
