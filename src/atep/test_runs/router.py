from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, WebSocket, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.test_runs.realtime import publish_test_run_update, stream_test_run
from atep.test_runs.schemas import (
    RUN_ID_PATTERN,
    TestRunCreate,
    TestRunPage,
    TestRunResponse,
    TestRunStatus,
    TestRunStatusUpdate,
    TestRunStreamEvent,
    test_run_response,
)
from atep.test_runs.service import (
    create_test_run,
    list_test_runs,
    require_test_run,
    update_test_run_status,
)
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/test-runs", tags=["test-runs"])
websocket_router = APIRouter(prefix="/test-runs", tags=["test-runs"])
test_runs_read = require_permissions(PermissionName.TEST_RUNS_READ.value)
test_runs_write = require_permissions(PermissionName.TEST_RUNS_WRITE.value)


@router.post("", response_model=TestRunResponse, status_code=status.HTTP_201_CREATED)
async def create_test_run_endpoint(
    command: TestRunCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(test_runs_write)],
) -> TestRunResponse:
    vehicle = await require_vehicle(session, command.vehicle_id)
    test_run, duplicate = await create_test_run(
        session,
        command=command,
        vehicle=vehicle,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    result = test_run_response(test_run, vehicle.identifier)
    if not duplicate:
        await publish_test_run_update(
            request.app.state.redis,
            TestRunStreamEvent(
                type="atep.test_run.created.v1", test_run=result, occurred_at=datetime.now(UTC)
            ),
        )
    return result


@router.get("", response_model=TestRunPage)
async def list_test_runs_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(test_runs_read)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[TestRunStatus | None, Query(alias="status")] = None,
    vehicle_id: Annotated[str | None, Query(min_length=3, max_length=80)] = None,
) -> TestRunPage:
    rows, total = await list_test_runs(
        session,
        limit=limit,
        offset=offset,
        status=status_filter,
        vehicle_identifier=vehicle_id,
    )
    return TestRunPage(
        items=[test_run_response(item, vehicle.identifier) for item, vehicle in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=TestRunResponse)
async def get_test_run_endpoint(
    run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(test_runs_read)],
) -> TestRunResponse:
    test_run, vehicle = await require_test_run(session, run_id)
    return test_run_response(test_run, vehicle.identifier)


@router.patch("/{run_id}/status", response_model=TestRunResponse)
async def update_test_run_status_endpoint(
    run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN.pattern)],
    command: TestRunStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(test_runs_write)],
) -> TestRunResponse:
    test_run, vehicle = await require_test_run(session, run_id, for_update=True)
    updated, duplicate = await update_test_run_status(
        session,
        test_run=test_run,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    result = test_run_response(updated, vehicle.identifier)
    if not duplicate:
        await publish_test_run_update(
            request.app.state.redis,
            TestRunStreamEvent(
                type="atep.test_run.updated.v1", test_run=result, occurred_at=datetime.now(UTC)
            ),
        )
    return result


@websocket_router.websocket("/{run_id}/stream")
async def stream_test_run_endpoint(
    websocket: WebSocket,
    run_id: Annotated[str, Path(pattern=RUN_ID_PATTERN.pattern)],
) -> None:
    await stream_test_run(websocket, run_id)
