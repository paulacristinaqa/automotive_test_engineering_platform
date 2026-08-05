from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.environment_profiles.service import require_active_environment_profile
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.test_jobs.schemas import (
    JOB_ID_PATTERN,
    TestJobCancel,
    TestJobCreate,
    TestJobPage,
    TestJobResponse,
    TestJobStatus,
    test_job_response,
)
from atep.test_jobs.service import (
    cancel_test_job,
    create_test_job,
    list_test_jobs,
    require_test_job,
)
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/test-jobs", tags=["test-jobs"])
test_jobs_read = require_permissions(PermissionName.TEST_JOBS_READ.value)
test_jobs_manage = require_permissions(PermissionName.TEST_JOBS_MANAGE.value)


@router.post("", response_model=TestJobResponse, status_code=status.HTTP_201_CREATED)
async def create_test_job_endpoint(
    command: TestJobCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(test_jobs_manage)],
) -> TestJobResponse:
    vehicle = await require_vehicle(session, command.vehicle_id)
    profile = (
        await require_active_environment_profile(session, command.environment_profile_id)
        if command.environment_profile_id is not None
        else None
    )
    job, duplicate = await create_test_job(
        session,
        command=command,
        vehicle=vehicle,
        environment_profile=profile,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return test_job_response(job, vehicle.identifier)


@router.get("", response_model=TestJobPage)
async def list_test_jobs_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(test_jobs_read)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[TestJobStatus | None, Query(alias="status")] = None,
    vehicle_id: Annotated[str | None, Query(min_length=3, max_length=80)] = None,
) -> TestJobPage:
    rows, total = await list_test_jobs(
        session,
        limit=limit,
        offset=offset,
        status=status_filter,
        vehicle_identifier=vehicle_id,
    )
    return TestJobPage(
        items=[test_job_response(job, vehicle.identifier) for job, vehicle in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=TestJobResponse)
async def get_test_job_endpoint(
    job_id: Annotated[str, Path(pattern=JOB_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(test_jobs_read)],
) -> TestJobResponse:
    job, vehicle = await require_test_job(session, job_id)
    return test_job_response(job, vehicle.identifier)


@router.patch("/{job_id}/cancel", response_model=TestJobResponse)
async def cancel_test_job_endpoint(
    job_id: Annotated[str, Path(pattern=JOB_ID_PATTERN.pattern)],
    command: TestJobCancel,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(test_jobs_manage)],
) -> TestJobResponse:
    job, vehicle = await require_test_job(session, job_id, for_update=True)
    job, _ = await cancel_test_job(
        session,
        job=job,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return test_job_response(job, vehicle.identifier)
