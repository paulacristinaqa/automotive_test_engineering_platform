from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from atep.dashboard.schemas import DashboardOverview
from atep.dashboard.service import build_overview
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
read_access = require_permissions(PermissionName.DASHBOARD_READ.value)


@router.get("/overview", response_model=DashboardOverview)
async def dashboard_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    window_hours: Annotated[int, Query(ge=1, le=720)] = 24,
    evidence_limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> DashboardOverview:
    return await build_overview(session, window_hours=window_hours, evidence_limit=evidence_limit)
