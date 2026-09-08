from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.fault_campaigns.schemas import (
    CAMPAIGN_ID_PATTERN,
    STEP_ID_PATTERN,
    FaultCampaignCreate,
    FaultCampaignPage,
    FaultCampaignResponse,
    FaultCampaignStatus,
    FaultCampaignStatusUpdate,
    FaultExecutionCancel,
    FaultExecutionCreate,
    FaultExecutionPage,
    FaultExecutionResponse,
    FaultExecutionStatus,
    FaultStepResultPage,
    FaultStepResultResponse,
    FaultStepResultUpdate,
)
from atep.fault_campaigns.service import (
    campaign_response,
    cancel_execution,
    create_campaign,
    create_execution,
    execution_response,
    list_campaigns,
    list_executions,
    list_step_results,
    require_campaign,
    require_execution,
    require_step_result,
    step_result_response,
    update_campaign_status,
    update_step_result,
)
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.test_runs.service import require_test_run
from atep.vehicles.service import require_vehicle

router = APIRouter(tags=["fault-campaigns"])
campaign_read = require_permissions(PermissionName.TEST_CATALOG_READ.value)
campaign_manage = require_permissions(PermissionName.TEST_CATALOG_MANAGE.value)


@router.post(
    "/fault-campaigns",
    response_model=FaultCampaignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign_endpoint(
    command: FaultCampaignCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(campaign_manage)],
) -> FaultCampaignResponse:
    campaign, duplicate = await create_campaign(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return campaign_response(campaign)


@router.get("/fault-campaigns", response_model=FaultCampaignPage)
async def list_campaigns_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(campaign_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[FaultCampaignStatus | None, Query(alias="status")] = None,
) -> FaultCampaignPage:
    campaigns, total = await list_campaigns(
        session, limit=limit, offset=offset, status=status_filter
    )
    return FaultCampaignPage(
        items=[campaign_response(item) for item in campaigns],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/fault-campaigns/{campaign_id}", response_model=FaultCampaignResponse)
async def get_campaign_endpoint(
    campaign_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(campaign_read)],
) -> FaultCampaignResponse:
    return campaign_response(await require_campaign(session, campaign_id))


@router.patch("/fault-campaigns/{campaign_id}/status", response_model=FaultCampaignResponse)
async def update_campaign_status_endpoint(
    campaign_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN.pattern)],
    command: FaultCampaignStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(campaign_manage)],
) -> FaultCampaignResponse:
    campaign = await require_campaign(session, campaign_id, for_update=True)
    campaign, _ = await update_campaign_status(
        session,
        campaign=campaign,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return campaign_response(campaign)


@router.post(
    "/fault-campaigns/{campaign_id}/executions",
    response_model=FaultExecutionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_execution_endpoint(
    campaign_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN.pattern)],
    command: FaultExecutionCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(campaign_manage)],
) -> FaultExecutionResponse:
    campaign = await require_campaign(session, campaign_id)
    vehicle = await require_vehicle(session, command.vehicle_id)
    test_run = None
    if command.test_run_id is not None:
        test_run, _ = await require_test_run(session, command.test_run_id)
    execution, duplicate = await create_execution(
        session,
        campaign=campaign,
        command=command,
        vehicle=vehicle,
        test_run=test_run,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return execution_response(execution, campaign, vehicle)


@router.get("/fault-executions", response_model=FaultExecutionPage)
async def list_executions_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(campaign_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[FaultExecutionStatus | None, Query(alias="status")] = None,
    vehicle_id: Annotated[str | None, Query(min_length=3, max_length=80)] = None,
) -> FaultExecutionPage:
    rows, total = await list_executions(
        session,
        limit=limit,
        offset=offset,
        status=status_filter,
        vehicle_identifier=vehicle_id,
    )
    return FaultExecutionPage(
        items=[
            execution_response(execution, campaign, vehicle)
            for execution, campaign, vehicle in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/fault-executions/{execution_id}", response_model=FaultExecutionResponse)
async def get_execution_endpoint(
    execution_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(campaign_read)],
) -> FaultExecutionResponse:
    execution, campaign, vehicle = await require_execution(session, execution_id)
    return execution_response(execution, campaign, vehicle)


@router.get("/fault-executions/{execution_id}/steps", response_model=FaultStepResultPage)
async def list_execution_steps_endpoint(
    execution_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN.pattern)],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(campaign_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> FaultStepResultPage:
    execution, _campaign, _vehicle = await require_execution(session, execution_id)
    results, total = await list_step_results(
        session, execution=execution, limit=limit, offset=offset
    )
    return FaultStepResultPage(
        items=[step_result_response(item, execution.execution_id) for item in results],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/fault-executions/{execution_id}/steps/{step_id}",
    response_model=FaultStepResultResponse,
)
async def update_execution_step_endpoint(
    execution_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN.pattern)],
    step_id: Annotated[str, Path(pattern=STEP_ID_PATTERN.pattern)],
    command: FaultStepResultUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(campaign_manage)],
) -> FaultStepResultResponse:
    execution, campaign, vehicle = await require_execution(session, execution_id, for_update=True)
    result = await require_step_result(
        session, execution=execution, step_id=step_id, for_update=True
    )
    result, _ = await update_step_result(
        session,
        execution=execution,
        campaign=campaign,
        vehicle=vehicle,
        result=result,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return step_result_response(result, execution.execution_id)


@router.patch("/fault-executions/{execution_id}/cancel", response_model=FaultExecutionResponse)
async def cancel_execution_endpoint(
    execution_id: Annotated[str, Path(pattern=CAMPAIGN_ID_PATTERN.pattern)],
    command: FaultExecutionCancel,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(campaign_manage)],
) -> FaultExecutionResponse:
    execution, campaign, vehicle = await require_execution(session, execution_id, for_update=True)
    execution, _ = await cancel_execution(
        session,
        execution=execution,
        campaign=campaign,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return execution_response(execution, campaign, vehicle)
