from __future__ import annotations

import asyncio
import tempfile
from collections import Counter
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Tuple, Union

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.session as db_session
from app.db.session import get_db
from app.main import app
from app.models.base import Base
from app.models.exclusion import UnitExclusion
from app.models.hours import HoursLedger
from app.models.schedule import PTOEntry, ScheduleEntry
from app.models.staff import (
    EmploymentClass as ModelEmploymentClass,
    LicenseType as ModelLicenseType,
    StaffCrossTraining,
    StaffMaster,
    StaffOps,
)
from app.models.unit import ShiftLabel as ModelShiftLabel
from app.models.unit import Unit, UnitTypology as ModelUnitTypology
from app.services import recommendation as recommendation_service
from tests.scenarios.models import (
    AssertionResult,
    CalloutActionSpec,
    GenerateScheduleActionSpec,
    ScenarioAssertion,
    ScenarioResult,
    ScenarioRunReport,
    ScenarioSetup,
    ScenarioSpec,
)
from tests.scenarios.specs import SCENARIOS


@contextmanager
def _stub_rationales():
    async def fake_generate_rationales(candidates, **_kwargs):
        rationales = [
            (
                f"- Hours: {candidate.ot_headroom_description}\n"
                f"- Experience: {candidate.license} — {candidate.clinical_fit_description}\n"
                f"- Distance: {candidate.distance_miles:.1f} miles from facility"
            )
            for candidate in candidates
        ]
        return rationales, "template"

    original = recommendation_service.generate_rationales
    recommendation_service.generate_rationales = fake_generate_rationales
    try:
        yield
    finally:
        recommendation_service.generate_rationales = original


@asynccontextmanager
async def _scenario_environment() -> AsyncIterator[Tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    with tempfile.TemporaryDirectory(prefix="scenario-report-") as temp_dir:
        db_path = Path(temp_dir) / "scenario.db"
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        # The POST /callouts background task opens its own session via
        # db_session.async_session_factory — redirect that at the SQLite
        # factory so tests don't hit the production Postgres pool.
        original_factory = db_session.async_session_factory
        db_session.async_session_factory = session_factory

        try:
            with _stub_rationales():
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://scenario.local",
                ) as client:
                    yield client, session_factory
        finally:
            app.dependency_overrides.pop(get_db, None)
            db_session.async_session_factory = original_factory
            await engine.dispose()


async def _seed_setup(session_factory: async_sessionmaker[AsyncSession], setup: ScenarioSetup) -> None:
    async with session_factory() as session:
        for unit in setup.units:
            session.add(
                Unit(
                    unit_id=unit.unit_id,
                    name=unit.name,
                    typology=ModelUnitTypology(unit.typology.value),
                    required_ratio=unit.required_ratio,
                    is_active=unit.is_active,
                )
            )

        for staff in setup.staff:
            session.add(
                StaffMaster(
                    employee_id=staff.employee_id,
                    name=staff.name,
                    license=ModelLicenseType(staff.license.value),
                    employment_class=ModelEmploymentClass(staff.employment_class),
                    zip_code=staff.zip_code,
                    is_active=staff.is_active,
                )
            )
            session.add(
                StaffOps(
                    employee_id=staff.employee_id,
                    home_unit_id=staff.home_unit_id,
                    hire_date=staff.hire_date,
                )
            )
            for unit_id in staff.cross_trained_unit_ids:
                session.add(
                    StaffCrossTraining(
                        employee_id=staff.employee_id,
                        unit_id=unit_id,
                    )
                )

        for record in setup.hours_ledgers:
            session.add(
                HoursLedger(
                    employee_id=record.employee_id,
                    cycle_start_date=record.cycle_start_date,
                    hours_this_cycle=record.hours_this_cycle,
                    shift_count_this_biweek=record.shift_count_this_biweek,
                    updated_at=datetime.now(timezone.utc),
                )
            )

        for entry in setup.schedule_entries:
            session.add(
                ScheduleEntry(
                    employee_id=entry.employee_id,
                    unit_id=entry.unit_id,
                    shift_date=entry.shift_date,
                    shift_label=ModelShiftLabel(entry.shift_label.value),
                    is_published=entry.is_published,
                    is_clocked_in=entry.is_clocked_in,
                )
            )

        for pto in setup.pto_entries:
            session.add(
                PTOEntry(
                    employee_id=pto.employee_id,
                    start_date=pto.start_date,
                    end_date=pto.end_date,
                )
            )

        for exclusion in setup.exclusions:
            session.add(
                UnitExclusion(
                    employee_id=exclusion.employee_id,
                    unit_id=exclusion.unit_id,
                    reason=exclusion.reason,
                    effective_from=exclusion.effective_from,
                    effective_until=exclusion.effective_until,
                )
            )

        await session.commit()


async def _execute_action(
    client: AsyncClient,
    action: Union[CalloutActionSpec, GenerateScheduleActionSpec],
) -> Tuple[dict[str, Any], Optional[str]]:
    try:
        if isinstance(action, CalloutActionSpec):
            response = await client.post(
                "/callouts",
                json=action.request.model_dump(mode="json"),
            )
            response.raise_for_status()
            job = response.json()

            # Poll the background job until it terminates. The pipeline
            # runs in-process via asyncio.create_task; a handful of
            # short sleeps is plenty for the scenario fixtures.
            callout_id = job.get("callout_id")
            deadline_iters = 200  # ~10s at 50ms each
            for _ in range(deadline_iters):
                status = job.get("status")
                if status in ("COMPLETED", "FAILED"):
                    break
                await asyncio.sleep(0.05)
                poll = await client.get(f"/callouts/{callout_id}")
                poll.raise_for_status()
                job = poll.json()
            if job.get("status") == "FAILED":
                raise RuntimeError(
                    f"Callout job failed: {job.get('error_message') or 'unknown error'}"
                )
            return {"callout": job}, None

        response = await client.post(
            "/schedule/generate",
            json=action.request.model_dump(mode="json"),
        )
        response.raise_for_status()

        responses: dict[str, Any] = {"generate_schedule": response.json()}
        if action.fetch_monthly:
            monthly = await client.get(
                f"/schedule/monthly?year={action.request.year}&month={action.request.month}"
            )
            monthly.raise_for_status()
            responses["monthly_schedule"] = monthly.json()

        if action.fetch_work_hours:
            work_hours = await client.get(
                f"/schedule/work-hours?year={action.request.year}&month={action.request.month}"
            )
            work_hours.raise_for_status()
            responses["work_hours"] = work_hours.json()

        return responses, None
    except Exception as exc:  # pragma: no cover - exercised indirectly in tests
        return {}, str(exc)


def _callout_candidates(responses: dict[str, Any]) -> list[dict[str, Any]]:
    return responses.get("callout", {}).get("candidates", [])


def _monthly_slots(responses: dict[str, Any]) -> list[dict[str, Any]]:
    monthly = responses.get("monthly_schedule", {})
    days = monthly.get("days", [])
    return [slot for day in days for slot in day.get("slots", [])]


def _find_slot(
    responses: dict[str, Any],
    unit_id: str,
    shift_date: str,
    shift_label: str,
) -> Optional[dict[str, Any]]:
    for slot in _monthly_slots(responses):
        if (
            slot.get("unit_id") == unit_id
            and slot.get("shift_date") == shift_date
            and slot.get("shift_label") == shift_label
        ):
            return slot
    return None


def _evaluate_assertion(assertion: ScenarioAssertion, responses: dict[str, Any]) -> AssertionResult:
    kind = assertion.kind
    params = assertion.params
    detail = ""
    passed = False

    if kind == "top_candidate_is":
        top_candidate = _callout_candidates(responses)[0]["employee_id"] if _callout_candidates(responses) else None
        expected = params["employee_id"]
        passed = top_candidate == expected
        detail = f"expected top={expected}, actual top={top_candidate}"
    elif kind == "candidate_not_present":
        employee_id = params["employee_id"]
        candidates = {candidate["employee_id"] for candidate in _callout_candidates(responses)}
        passed = employee_id not in candidates
        detail = f"candidate list={sorted(candidates)}"
    elif kind == "excluded_employee_never_assigned":
        employee_id = params["employee_id"]
        candidates = {candidate["employee_id"] for candidate in _callout_candidates(responses)}
        monthly_assignees = {
            emp["employee_id"]
            for slot in _monthly_slots(responses)
            for emp in slot.get("assigned_employees", [])
        }
        passed = employee_id not in candidates and employee_id not in monthly_assignees
        detail = (
            f"in_candidates={employee_id in candidates}, "
            f"in_monthly_assignments={employee_id in monthly_assignees}"
        )
    elif kind == "no_rest_window_violation":
        employee_id = params["employee_id"]
        candidates = {candidate["employee_id"] for candidate in _callout_candidates(responses)}
        filtered = responses.get("callout", {}).get("filter_stats", {}).get("filtered_out", {})
        passed = employee_id not in candidates and filtered.get("rest_window_violation", 0) >= 1
        detail = f"candidate_present={employee_id in candidates}, rest_window_count={filtered.get('rest_window_violation', 0)}"
    elif kind == "minimum_hours_priority_observed":
        top_candidate = _callout_candidates(responses)[0]["employee_id"] if _callout_candidates(responses) else None
        expected = params["employee_id"]
        passed = top_candidate == expected
        detail = f"expected priority candidate={expected}, actual top={top_candidate}"
    elif kind == "scenario_label_is":
        actual = responses.get("generate_schedule", {}).get("scenario")
        expected = params["value"]
        passed = actual == expected
        detail = f"expected scenario={expected}, actual={actual}"
    elif kind == "unfilled_slots_at_most":
        actual = responses.get("generate_schedule", {}).get("unfilled_slots")
        limit = params["max_unfilled"]
        passed = isinstance(actual, int) and actual <= limit
        detail = f"unfilled_slots={actual}, allowed<={limit}"
    elif kind == "warning_count_at_most":
        warnings = responses.get("generate_schedule", {}).get("warnings", [])
        limit = params["max_warnings"]
        passed = len(warnings) <= limit
        detail = f"warning_count={len(warnings)}, allowed<={limit}"
    elif kind == "no_unassigned_slots":
        unassigned = [
            slot
            for slot in _monthly_slots(responses)
            if slot.get("status") == "unassigned"
        ]
        passed = not unassigned
        detail = f"unassigned_slots={len(unassigned)}"
    elif kind == "slot_assigned_license_in":
        slot = _find_slot(
            responses,
            unit_id=params["unit_id"],
            shift_date=params["shift_date"],
            shift_label=params["shift_label"],
        )
        allowed = set(params["licenses"])
        licenses = {employee["license"] for employee in slot.get("assigned_employees", [])} if slot else set()
        passed = bool(slot) and bool(licenses & allowed)
        detail = f"slot_found={bool(slot)}, assigned_licenses={sorted(licenses)}, allowed={sorted(allowed)}"
    elif kind == "subacute_slots_filled_before_lt":
        _FILLED = {"fully_staffed", "partially_staffed"}
        subacute_filled = sum(
            1
            for slot in _monthly_slots(responses)
            if slot.get("unit_id") == params["subacute_unit_id"] and slot.get("status") in _FILLED
        )
        lt_filled = sum(
            1
            for slot in _monthly_slots(responses)
            if slot.get("unit_id") == params["lt_unit_id"] and slot.get("status") in _FILLED
        )
        passed = subacute_filled >= lt_filled
        detail = f"subacute_assigned={subacute_filled}, lt_assigned={lt_filled}"
    else:  # pragma: no cover - catches spec mistakes
        detail = f"Unsupported assertion kind: {kind}"

    return AssertionResult(
        kind=kind,
        description=assertion.description,
        passed=passed,
        detail=detail,
    )


async def run_scenario(spec: ScenarioSpec) -> ScenarioResult:
    async with _scenario_environment() as (client, session_factory):
        await _seed_setup(session_factory, spec.setup)
        responses, execution_error = await _execute_action(client, spec.action)

    if execution_error is not None:
        return ScenarioResult(
            id=spec.id,
            title=spec.title,
            business_rule=spec.business_rule,
            expected_classification=spec.result_classification,
            actual_classification="fail",
            assertions=[
                AssertionResult(
                    kind="execution",
                    description="Scenario should execute successfully.",
                    passed=False,
                    detail=execution_error,
                )
            ],
            request=spec.action.request.model_dump(mode="json"),
            responses={"error": execution_error},
        )

    assertion_results = [
        _evaluate_assertion(assertion, responses)
        for assertion in spec.expected_assertions
    ]
    all_passed = all(result.passed for result in assertion_results)
    if all_passed:
        actual_classification = "pass"
    elif spec.result_classification == "gap":
        actual_classification = "gap"
    else:
        actual_classification = "fail"

    return ScenarioResult(
        id=spec.id,
        title=spec.title,
        business_rule=spec.business_rule,
        expected_classification=spec.result_classification,
        actual_classification=actual_classification,
        assertions=assertion_results,
        request=spec.action.request.model_dump(mode="json"),
        responses=responses,
    )


async def run_scenario_suite() -> ScenarioRunReport:
    scenarios = [await run_scenario(spec) for spec in SCENARIOS]
    summary = Counter(result.actual_classification for result in scenarios)
    return ScenarioRunReport(
        generated_at=datetime.now(timezone.utc),
        scenarios=scenarios,
        summary={
            "pass": summary.get("pass", 0),
            "gap": summary.get("gap", 0),
            "fail": summary.get("fail", 0),
            "total": len(scenarios),
        },
    )
