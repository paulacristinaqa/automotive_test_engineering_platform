from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.performance_testing.schemas import (
    PerformanceExecutionCreate,
    PerformanceExecutionPage,
    PerformanceExecutionResponse,
    PerformanceProfileCreate,
    PerformanceProfilePage,
    PerformanceProfileResponse,
)
from atep.performance_testing.service import (
    create_execution,
    create_profile,
    execution_response,
    list_executions,
    list_profiles,
    profile_response,
    require_execution,
    require_profile,
)
from atep.test_runs.service import require_test_run

router = APIRouter(prefix="/performance", tags=["performance-and-stress"])
read_access = require_permissions(PermissionName.TEST_CATALOG_READ.value)
manage_access = require_permissions(PermissionName.TEST_CATALOG_MANAGE.value)
slug = Path(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")


@router.post("/profiles", response_model=PerformanceProfileResponse, status_code=201)
async def create_profile_endpoint(
    command: PerformanceProfileCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> PerformanceProfileResponse:
    profile, duplicate = await create_profile(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return profile_response(profile, duplicate)


@router.get("/profiles", response_model=PerformanceProfilePage)
async def list_profiles_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> PerformanceProfilePage:
    rows, total = await list_profiles(session, limit, offset)
    return PerformanceProfilePage(
        items=[profile_response(item) for item in rows], total=total, limit=limit, offset=offset
    )


@router.get("/profiles/{profile_id}", response_model=PerformanceProfileResponse)
async def get_profile_endpoint(
    profile_id: Annotated[str, slug],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> PerformanceProfileResponse:
    return profile_response(await require_profile(session, profile_id))


@router.post(
    "/profiles/{profile_id}/executions",
    response_model=PerformanceExecutionResponse,
    status_code=201,
)
async def create_execution_endpoint(
    profile_id: Annotated[str, slug],
    command: PerformanceExecutionCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> PerformanceExecutionResponse:
    profile = await require_profile(session, profile_id)
    test_run, _ = await require_test_run(session, command.test_run_id)
    baseline = (
        await require_execution(session, command.baseline_execution_id)
        if command.baseline_execution_id
        else None
    )
    execution, duplicate = await create_execution(
        session,
        profile=profile,
        test_run=test_run,
        baseline=baseline,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return execution_response(execution, profile, test_run, baseline, duplicate)


@router.get("/profiles/{profile_id}/executions", response_model=PerformanceExecutionPage)
async def list_executions_endpoint(
    profile_id: Annotated[str, slug],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> PerformanceExecutionPage:
    profile = await require_profile(session, profile_id)
    rows, total = await list_executions(session, profile, limit, offset)
    return PerformanceExecutionPage(
        items=[execution_response(item, profile, run, baseline) for item, run, baseline in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
