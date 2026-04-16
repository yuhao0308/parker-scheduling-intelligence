# Scheduling Scenario Report

Generated: `2026-04-15T16:54:43.660777+00:00`

## Summary

- Pass: 6
- Gap: 1
- Fail: 0
- Total: 7

## Subacute callout ranks the best clinically appropriate CNA first

- ID: `callout-subacute-best-fit`
- Expected classification: `pass`
- Actual classification: `pass`
- Business rule: When a Subacute CNA calls out, the top replacement should favor lower overtime exposure and stronger Short-Term fit over weaker clinical matches.

### Request

```json
{
  "callout_employee_id": "CNA-CALL",
  "unit_id": "U-SA1",
  "shift_date": "2026-04-14",
  "shift_label": "DAY"
}
```

### Assertions

- [PASS] The home-unit CNA with straight-time headroom should rank first.  
  Detail: `expected top=CNA-HOME, actual top=CNA-HOME`

## Unit exclusions remove the otherwise best-fit candidate

- ID: `callout-exclusion-enforced`
- Expected classification: `pass`
- Actual classification: `pass`
- Business rule: A staff member excluded from a unit must never appear in recommendations for that unit, even if they would otherwise rank first.

### Request

```json
{
  "callout_employee_id": "CNA-CALL",
  "unit_id": "U-SA1",
  "shift_date": "2026-04-15",
  "shift_label": "DAY"
}
```

### Assertions

- [PASS] The excluded employee should not appear in the recommendation list.  
  Detail: `candidate list=['CNA-BACKUP']`
- [PASS] The excluded employee should be fully blocked for the target unit.  
  Detail: `in_candidates=False, in_monthly_assignments=False`
- [PASS] The cross-trained backup should become the top valid candidate.  
  Detail: `expected top=CNA-BACKUP, actual top=CNA-BACKUP`

## Rest-window conflicts remove candidates with adjacent shifts

- ID: `callout-rest-window-enforced`
- Expected classification: `pass`
- Actual classification: `pass`
- Business rule: A candidate who would exceed the allowed operational-day shift load must be filtered out before scoring.

### Request

```json
{
  "callout_employee_id": "CNA-CALL",
  "unit_id": "U-SA1",
  "shift_date": "2026-04-10",
  "shift_label": "EVENING"
}
```

### Assertions

- [PASS] The candidate with adjacent shifts should be filtered out.  
  Detail: `candidate list=['CNA-SAFE']`
- [PASS] No rest-window-violating candidate should remain in the ranked list.  
  Detail: `candidate_present=False, rest_window_count=1`
- [PASS] The safe candidate should be the best remaining option.  
  Detail: `expected top=CNA-SAFE, actual top=CNA-SAFE`

## Monthly generation keeps Subacute licensed and LT certified where possible

- ID: `schedule-bucket-preference`
- Expected classification: `pass`
- Actual classification: `pass`
- Business rule: With sufficient staffing, Subacute shifts should be filled from the licensed bucket and Long-Term shifts from the certified bucket.

### Request

```json
{
  "year": 2026,
  "month": 4,
  "staff_count_override": null
}
```

### Assertions

- [PASS] Sufficient staffing should produce the ideal scenario label.  
  Detail: `expected scenario=ideal, actual=ideal`
- [PASS] The first Subacute day shift should be covered by a licensed staff member.  
  Detail: `slot_found=True, assigned_licenses=['RN'], allowed=['LPN', 'RN']`
- [PASS] The first LT day shift should be covered by a certified staff member.  
  Detail: `slot_found=True, assigned_licenses=['CNA'], allowed=['CNA', 'PCT']`

## Staff shortages preserve Subacute coverage ahead of LT

- ID: `schedule-shortage-subacute-priority`
- Expected classification: `pass`
- Actual classification: `pass`
- Business rule: When staffing is insufficient, higher-acuity Subacute coverage should be filled before lower-priority Long-Term coverage.

### Request

```json
{
  "year": 2026,
  "month": 4,
  "staff_count_override": null
}
```

### Assertions

- [PASS] Severe understaffing should show up in the scenario badge.  
  Detail: `expected scenario=critical, actual=critical`
- [PASS] Subacute should retain at least as many filled slots as Long-Term under shortage.  
  Detail: `subacute_assigned=25, lt_assigned=0`

## Minimum-hours-first fairness is still a known gap

- ID: `minimum-hours-priority-gap`
- Expected classification: `gap`
- Actual classification: `gap`
- Business rule: A full-time employee who needs hours should be prioritized ahead of a per-diem employee taking extra shifts, even when the per-diem worker has a stronger home-unit match.

### Request

```json
{
  "callout_employee_id": "CNA-CALL",
  "unit_id": "U-LT1",
  "shift_date": "2026-04-16",
  "shift_label": "DAY"
}
```

### Assertions

- [MISS] The full-time employee who needs hours should outrank the per-diem employee.  
  Detail: `expected priority candidate=CNA-FT-NEEDS-HOURS, actual top=CNA-PD-HOME`

## Ideal monthly generation produces full coverage with no hidden warnings

- ID: `schedule-ideal-month-summary`
- Expected classification: `pass`
- Actual classification: `pass`
- Business rule: With enough staff for the simplified monthly model, the generated month should be fully covered, ideal, and free of hidden warning noise.

### Request

```json
{
  "year": 2026,
  "month": 4,
  "staff_count_override": null
}
```

### Assertions

- [PASS] The summary badge should report ideal coverage.  
  Detail: `expected scenario=ideal, actual=ideal`
- [PASS] Ideal coverage should have no unfilled slots.  
  Detail: `unfilled_slots=0, allowed<=0`
- [PASS] Ideal coverage should not generate warning rows.  
  Detail: `warning_count=0, allowed<=0`
- [PASS] The monthly schedule view should show every slot assigned.  
  Detail: `unassigned_slots=0`
