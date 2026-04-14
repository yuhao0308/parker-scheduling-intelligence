"""Recommendation orchestrator: filter → score → rank → explain.

This is the main pipeline. When a call-out is reported, this service:
1. Loads all active staff from DB
2. Builds the schedule/exclusion context
3. Runs hard filters to eliminate ineligible candidates
4. Scores each surviving candidate
5. Ranks by descending score
6. Generates rationale via local LLM (with template fallback)
7. Logs the recommendation
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.exceptions import NoCandidatesError, UnitNotFoundError
from app.models.hours import HoursLedger
from app.models.recommendation import RecommendationLog
from app.models.staff import StaffMaster
from app.models.unit import Unit
from app.schemas.callout import CalloutRequest, CalloutResponse
from app.schemas.candidate import FilterStats, ScoreBreakdown, ScoredCandidate
from app.schemas.common import LicenseType, ShiftLabel, UnitTypology
from app.services.filter import (
    CandidateRecord,
    ExclusionRecord,
    FilterResult,
    ScheduleContext,
    apply_hard_filters,
)
from app.services.overtime import (
    BIWEEKLY_SHIFT_OT_THRESHOLD,
    WEEKLY_OT_THRESHOLD_HOURS,
    calculate_ot_headroom,
)
from app.services.proximity import estimate_distance_miles, proximity_score
from app.services.rationale import CandidateSignals, generate_rationales
from app.services.scoring import (
    ScoreResult,
    ScoringConfig,
    compute_clinical_fit,
    compute_float_penalty,
    load_scoring_config,
    score_candidate,
)
from app.services.shift_utils import SHIFT_DURATION_HOURS
from app.services.staff_loader import (
    build_candidate_records,
    build_schedule_context,
    load_exclusions,
    load_hours_map,
    load_staff_pool,
)

logger = structlog.get_logger()


async def generate_recommendations(
    callout: CalloutRequest,
    callout_id: int,
    db: AsyncSession,
    settings: Settings,
) -> CalloutResponse:
    """Main recommendation pipeline."""

    # 1. Load target unit
    unit = await db.get(Unit, callout.unit_id)
    if not unit:
        raise UnitNotFoundError(callout.unit_id)

    target_typology = UnitTypology(unit.typology.value)
    required_license = await _infer_required_license(callout.callout_employee_id, db)

    # 2. Load scoring config
    scoring_config = load_scoring_config(settings.scoring_weights_path)

    # 3. Load all active staff with their ops and cross-training
    staff_list = await load_staff_pool(db)

    # 4. Build schedule context
    schedule_ctx = await build_schedule_context(db, callout.shift_date, callout.shift_label)

    # 5. Load exclusions
    exclusions = await load_exclusions(db, callout.unit_id, callout.shift_date)

    # 6. Build candidate records
    candidates = build_candidate_records(staff_list)

    # 7. Run hard filters
    filter_result = apply_hard_filters(
        candidates=candidates,
        required_license=required_license,
        schedule=schedule_ctx,
        exclusions=exclusions,
        target_unit_id=callout.unit_id,
        target_date=callout.shift_date,
        target_label=callout.shift_label,
    )

    logger.info(
        "filter_complete",
        total=filter_result.total_pool,
        passed=len(filter_result.passed),
        stats=filter_result.stats,
    )

    # 8. Score each surviving candidate
    scored = []
    hours_map = await load_hours_map(db)

    for cand in filter_result.passed:
        # OT headroom
        hours_rec = hours_map.get(cand.employee_id)
        hours_this_cycle = hours_rec.hours_this_cycle if hours_rec else 0.0
        shift_count_biweek = hours_rec.shift_count_this_biweek if hours_rec else 0

        employee_shifts = schedule_ctx.employee_shifts.get(cand.employee_id, [])

        ot_headroom, would_trigger_ot = calculate_ot_headroom(
            license_type=cand.license,
            hours_this_cycle=hours_this_cycle,
            shift_count_this_biweek=shift_count_biweek,
            employee_shifts=employee_shifts,
            target_date=callout.shift_date,
            target_label=callout.shift_label,
        )

        # Proximity
        dist_miles = estimate_distance_miles(cand.zip_code, settings.facility_zip_code)
        prox_score = proximity_score(
            dist_miles, scoring_config.max_relevant_distance_miles
        )

        # Clinical fit
        clin_fit = compute_clinical_fit(
            candidate_home_typology=UnitTypology(cand.home_unit_typology),
            candidate_cross_trained_unit_ids=cand.cross_trained_unit_ids,
            target_unit_id=callout.unit_id,
            target_typology=target_typology,
            home_unit_id=cand.home_unit_id,
            config=scoring_config,
        )

        # Float penalty
        float_pen = compute_float_penalty(
            home_unit_id=cand.home_unit_id,
            target_unit_id=callout.unit_id,
            candidate_home_typology=UnitTypology(cand.home_unit_typology),
            target_typology=target_typology,
            hire_date=cand.hire_date,
            reference_date=callout.shift_date,
            config=scoring_config,
        )

        # Historical acceptance (default 0.5 for Phase 1)
        hist_acceptance = 0.5

        # Score
        result = score_candidate(
            ot_headroom=ot_headroom,
            proximity=prox_score,
            clinical_fit=clin_fit,
            float_penalty=float_pen,
            historical_acceptance=hist_acceptance,
            weights=scoring_config.weights,
        )

        # Build OT description for rationale
        ot_desc = _ot_headroom_description(
            cand.license, hours_this_cycle, shift_count_biweek, would_trigger_ot
        )

        # Clinical fit description
        clin_desc = _clinical_fit_description(cand, callout.unit_id, target_typology)

        scored.append((cand, result, dist_miles, would_trigger_ot, ot_desc, clin_desc))

    # 9. Sort by score descending, take top N
    scored.sort(key=lambda x: x[1].total, reverse=True)
    scored = scored[: scoring_config.max_candidates_returned]

    # 10. Generate rationales
    signals = []
    for rank, (cand, res, dist, ot_trigger, ot_desc, clin_desc) in enumerate(scored, 1):
        signals.append(
            CandidateSignals(
                rank=rank,
                name=cand.name,
                license=cand.license.value,
                employment_class=cand.employment_class,
                home_unit=cand.home_unit_id,
                home_unit_typology=cand.home_unit_typology,
                target_unit=callout.unit_id,
                target_unit_typology=target_typology.value,
                ot_headroom_normalized=res.overtime_headroom,
                ot_headroom_description=ot_desc,
                would_trigger_ot=ot_trigger,
                distance_miles=dist,
                clinical_fit_score=res.clinical_fit,
                clinical_fit_description=clin_desc,
                is_home_unit=cand.home_unit_id == callout.unit_id,
                float_penalty=res.float_penalty,
                total_score=res.total,
            )
        )

    rationales, rationale_source = await generate_rationales(
        candidates=signals,
        unit_id=callout.unit_id,
        unit_typology=target_typology.value,
        shift_label=callout.shift_label.value,
        shift_date=str(callout.shift_date),
        settings=settings,
    )

    # 11. Build response
    response_candidates = []
    for i, (cand, res, *_) in enumerate(scored):
        response_candidates.append(
            ScoredCandidate(
                rank=i + 1,
                employee_id=cand.employee_id,
                name=cand.name,
                license=cand.license,
                employment_class=cand.employment_class,
                home_unit=cand.home_unit_id,
                score=res.total,
                score_breakdown=ScoreBreakdown(
                    overtime_headroom=res.overtime_headroom,
                    proximity=res.proximity,
                    clinical_fit=res.clinical_fit,
                    float_penalty=res.float_penalty,
                    historical_acceptance=res.historical_acceptance,
                    total=res.total,
                ),
                rationale=rationales[i] if i < len(rationales) else "",
                rationale_source=rationale_source,
            )
        )

    filter_stats = FilterStats(
        total_pool=filter_result.total_pool,
        passed_filter=len(filter_result.passed),
        filtered_out=filter_result.stats,
    )

    # 12. Log recommendation
    rec_log = RecommendationLog(
        callout_id=callout_id,
        request_timestamp=datetime.now(timezone.utc),
        target_unit_id=callout.unit_id,
        target_shift_label=callout.shift_label,
        target_shift_date=callout.shift_date,
        ranked_candidates=[c.model_dump() for c in response_candidates],
        filter_stats=filter_stats.model_dump(),
    )
    db.add(rec_log)
    await db.commit()

    return CalloutResponse(
        callout_id=callout_id,
        unit_id=callout.unit_id,
        unit_name=unit.name,
        shift_date=callout.shift_date,
        shift_label=callout.shift_label,
        candidates=response_candidates,
        filter_stats=filter_stats,
        generated_at=datetime.now(timezone.utc),
    )


# --- Helper functions ---


async def _infer_required_license(
    callout_employee_id: str, db: AsyncSession
) -> LicenseType:
    """Infer the required license from the calling-out employee's license.

    The replacement needs to be in the same license bucket (licensed or certified).
    """
    staff = await db.get(StaffMaster, callout_employee_id)
    if staff:
        return LicenseType(staff.license.value)
    return LicenseType.CNA



# _load_staff_pool, _build_candidate_records, _build_schedule_context,
# _load_exclusions, _load_hours_map were extracted to app/services/staff_loader.py


def _ot_headroom_description(
    license_type: LicenseType,
    hours_this_cycle: float,
    shift_count_biweek: int,
    would_trigger_ot: bool,
) -> str:
    """Generate a human-readable OT headroom description."""
    if license_type == LicenseType.RN:
        shifts_remaining = max(0, BIWEEKLY_SHIFT_OT_THRESHOLD - shift_count_biweek)
        if would_trigger_ot:
            return f"{shifts_remaining} shifts remaining in biweek (would trigger OT)"
        return f"{shifts_remaining} shifts remaining in biweek before OT"
    else:
        headroom = max(0.0, WEEKLY_OT_THRESHOLD_HOURS - hours_this_cycle)
        if would_trigger_ot:
            return f"{headroom:.1f}h remaining this week (would trigger OT)"
        return f"{headroom:.1f}h of straight time remaining this week"


def _clinical_fit_description(
    cand: CandidateRecord, target_unit_id: str, target_typology: UnitTypology
) -> str:
    """Generate a human-readable clinical fit description."""
    if cand.home_unit_id == target_unit_id:
        return "home unit — perfect fit"

    if target_unit_id in cand.cross_trained_unit_ids:
        return "cross-trained for this unit"

    home_typ = cand.home_unit_typology
    if home_typ == target_typology.value:
        return f"same typology ({home_typ})"

    if home_typ == "SUBACUTE" and target_typology == UnitTypology.LT:
        return "subacute-trained covering LT — acceptable"

    if home_typ == "LT" and target_typology == UnitTypology.SUBACUTE:
        return "LT-only covering subacute — clinical risk"

    return "unknown fit"
