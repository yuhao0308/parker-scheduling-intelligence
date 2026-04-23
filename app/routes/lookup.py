from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.deps import DbSession
from app.models.recommendation import OverrideLog, RecommendationLog
from app.models.schedule import Callout
from app.models.staff import StaffMaster, StaffOps
from app.models.unit import Unit

router = APIRouter(tags=["lookup"])


# ---------- response schemas ----------


class UnitOut(BaseModel):
    unit_id: str
    name: str
    typology: str


class StaffOut(BaseModel):
    employee_id: str
    name: str
    license: str
    employment_class: str
    home_unit_id: Optional[str] = None


class RecentCalloutOut(BaseModel):
    callout_id: int
    employee_id: str
    employee_name: Optional[str] = None
    employee_license: Optional[str] = None
    unit_id: str
    unit_name: Optional[str] = None
    shift_date: str
    shift_label: str
    reason: Optional[str] = None
    reported_at: str
    recommendation_id: Optional[int] = None
    ranked_candidates: Optional[list] = None
    filter_stats: Optional[dict] = None
    override_id: Optional[int] = None
    selected_employee_id: Optional[str] = None
    selected_employee_name: Optional[str] = None
    selected_employee_license: Optional[str] = None
    selected_rank: Optional[int] = None
    override_reason: Optional[str] = None


# ---------- endpoints ----------


@router.get("/units", response_model=List[UnitOut])
async def list_units(db: Annotated[AsyncSession, DbSession]):
    result = await db.execute(select(Unit).where(Unit.is_active == True).order_by(Unit.name))
    units = result.scalars().all()
    return [UnitOut(unit_id=u.unit_id, name=u.name, typology=u.typology.value) for u in units]


@router.get("/staff", response_model=List[StaffOut])
async def list_all_active_staff(db: Annotated[AsyncSession, DbSession]):
    """All active staff across units — feeds the Auto-Gen pool picker."""
    result = await db.execute(
        select(StaffMaster, StaffOps)
        .outerjoin(StaffOps, StaffMaster.employee_id == StaffOps.employee_id)
        .where(StaffMaster.is_active == True)
        .order_by(StaffMaster.name)
    )
    rows = result.all()
    return [
        StaffOut(
            employee_id=staff.employee_id,
            name=staff.name,
            license=staff.license.value,
            employment_class=staff.employment_class.value,
            home_unit_id=ops.home_unit_id if ops else None,
        )
        for staff, ops in rows
    ]


@router.get("/units/{unit_id}/staff", response_model=List[StaffOut])
async def list_staff_for_unit(unit_id: str, db: Annotated[AsyncSession, DbSession]):
    result = await db.execute(
        select(StaffMaster, StaffOps)
        .outerjoin(StaffOps, StaffMaster.employee_id == StaffOps.employee_id)
        .where(StaffMaster.is_active == True, StaffOps.home_unit_id == unit_id)
        .order_by(StaffMaster.name)
    )
    rows = result.all()
    return [
        StaffOut(
            employee_id=staff.employee_id,
            name=staff.name,
            license=staff.license.value,
            employment_class=staff.employment_class.value,
            home_unit_id=ops.home_unit_id if ops else None,
        )
        for staff, ops in rows
    ]


@router.get("/callouts/recent", response_model=List[RecentCalloutOut])
async def list_recent_callouts(
    db: Annotated[AsyncSession, DbSession],
    limit: int = Query(default=20, le=100),
):
    CallerStaff = aliased(StaffMaster)
    ReplacementStaff = aliased(StaffMaster)

    result = await db.execute(
        select(
            Callout,
            RecommendationLog,
            OverrideLog,
            CallerStaff,
            ReplacementStaff,
            Unit,
        )
        .outerjoin(RecommendationLog, Callout.id == RecommendationLog.callout_id)
        .outerjoin(OverrideLog, RecommendationLog.id == OverrideLog.recommendation_log_id)
        .outerjoin(CallerStaff, Callout.employee_id == CallerStaff.employee_id)
        .outerjoin(
            ReplacementStaff,
            OverrideLog.selected_employee_id == ReplacementStaff.employee_id,
        )
        .outerjoin(Unit, Callout.unit_id == Unit.unit_id)
        .order_by(Callout.reported_at.desc())
        .limit(limit)
    )
    rows = result.all()
    return [
        RecentCalloutOut(
            callout_id=c.id,
            employee_id=c.employee_id,
            employee_name=caller.name if caller else None,
            employee_license=caller.license.value if caller else None,
            unit_id=c.unit_id,
            unit_name=unit.name if unit else None,
            shift_date=c.shift_date.isoformat(),
            shift_label=c.shift_label.value,
            reason=c.reason,
            reported_at=c.reported_at.isoformat(),
            recommendation_id=rec.id if rec else None,
            ranked_candidates=rec.ranked_candidates if rec else None,
            filter_stats=rec.filter_stats if rec else None,
            override_id=ovr.id if ovr else None,
            selected_employee_id=ovr.selected_employee_id if ovr else None,
            selected_employee_name=replacement.name if replacement else None,
            selected_employee_license=replacement.license.value if replacement else None,
            selected_rank=ovr.selected_rank if ovr else None,
            override_reason=ovr.override_reason if ovr else None,
        )
        for c, rec, ovr, caller, replacement, unit in rows
    ]
