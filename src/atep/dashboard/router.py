from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from atep.dashboard.mobility import MobilityAnalytics, build_mobility_analytics
from atep.dashboard.schemas import (
    DashboardOverview,
    OperationalOverview,
    TestFailurePage,
    TestQualityTrends,
)
from atep.dashboard.service import (
    build_operations,
    build_overview,
    build_quality_trends,
    list_test_failures,
)
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
read_access = require_permissions(PermissionName.DASHBOARD_READ.value)


@router.get("/mobility", response_model=MobilityAnalytics)
async def mobility_analytics(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    window_hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> MobilityAnalytics:
    return await build_mobility_analytics(session, window_hours=window_hours)


@router.get("/operations", response_model=OperationalOverview)
async def operational_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    window_hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> OperationalOverview:
    return await build_operations(session, window_hours=window_hours)


@router.get("/overview", response_model=DashboardOverview)
async def dashboard_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    window_hours: Annotated[int, Query(ge=1, le=720)] = 24,
    evidence_limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> DashboardOverview:
    return await build_overview(session, window_hours=window_hours, evidence_limit=evidence_limit)


@router.get("/test-quality/trends", response_model=TestQualityTrends)
async def test_quality_trends(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    window_days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> TestQualityTrends:
    return await build_quality_trends(session, window_days=window_days)


@router.get("/test-quality/failures", response_model=TestFailurePage)
async def test_failure_drill_down(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    window_hours: Annotated[int, Query(ge=1, le=2160)] = 168,
    suite: Annotated[
        str | None, Query(min_length=1, max_length=24, pattern=r"^[a-z][a-z0-9_-]*$")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> TestFailurePage:
    return await list_test_failures(
        session,
        window_hours=window_hours,
        suite=suite,
        limit=limit,
        offset=offset,
    )
