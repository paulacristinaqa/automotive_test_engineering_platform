from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.mutation_analysis.schemas import (
    CampaignStatus,
    CampaignStatusUpdate,
    CoverageStatus,
    ExecutionStatus,
    MutantResultPage,
    MutantResultResponse,
    MutantResultUpdate,
    MutationCampaignCreate,
    MutationCampaignPage,
    MutationCampaignResponse,
    MutationExecutionCreate,
    MutationExecutionPage,
    MutationExecutionResponse,
    RequirementCoveragePage,
    RequirementCoverageResponse,
    RequirementCoverageUpsert,
)
from atep.mutation_analysis.service import (
    campaign_response,
    coverage_response,
    create_campaign,
    create_execution,
    execution_response,
    list_campaigns,
    list_coverage,
    list_executions,
    list_results,
    require_campaign,
    require_coverage,
    require_execution,
    require_result,
    result_response,
    update_campaign_status,
    update_result,
    upsert_requirement_coverage,
)
from atep.test_catalog.service import require_suite
from atep.test_runs.service import require_test_run
from atep.vehicles.service import require_vehicle

router = APIRouter(tags=["mutation-analysis"])
read_access = require_permissions(PermissionName.TEST_CATALOG_READ.value)
manage_access = require_permissions(PermissionName.TEST_CATALOG_MANAGE.value)
slug_path = Path(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")


@router.post("/mutation-campaigns", response_model=MutationCampaignResponse, status_code=201)
async def create_campaign_endpoint(
    command: MutationCampaignCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> MutationCampaignResponse:
    suite = await require_suite(session, command.catalog_suite_id)
    campaign, duplicate = await create_campaign(
        session,
        command=command,
        suite=suite,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return campaign_response(campaign, suite)


@router.get("/mutation-campaigns", response_model=MutationCampaignPage)
async def list_campaigns_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[CampaignStatus | None, Query(alias="status")] = None,
) -> MutationCampaignPage:
    rows, total = await list_campaigns(session, limit=limit, offset=offset, status=status_filter)
    return MutationCampaignPage(
        items=[campaign_response(campaign, suite) for campaign, suite in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/mutation-campaigns/{campaign_id}", response_model=MutationCampaignResponse)
async def get_campaign_endpoint(
    campaign_id: Annotated[str, slug_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> MutationCampaignResponse:
    campaign, suite = await require_campaign(session, campaign_id)
    return campaign_response(campaign, suite)


@router.patch("/mutation-campaigns/{campaign_id}/status", response_model=MutationCampaignResponse)
async def update_campaign_status_endpoint(
    campaign_id: Annotated[str, slug_path],
    command: CampaignStatusUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> MutationCampaignResponse:
    campaign, suite = await require_campaign(session, campaign_id, for_update=True)
    campaign, _ = await update_campaign_status(
        session,
        campaign=campaign,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return campaign_response(campaign, suite)


@router.post(
    "/mutation-campaigns/{campaign_id}/executions",
    response_model=MutationExecutionResponse,
    status_code=201,
)
async def create_execution_endpoint(
    campaign_id: Annotated[str, slug_path],
    command: MutationExecutionCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> MutationExecutionResponse:
    campaign, _ = await require_campaign(session, campaign_id)
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


@router.get("/mutation-executions", response_model=MutationExecutionPage)
async def list_executions_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[ExecutionStatus | None, Query(alias="status")] = None,
) -> MutationExecutionPage:
    rows, total = await list_executions(session, limit=limit, offset=offset, status=status_filter)
    return MutationExecutionPage(
        items=[execution_response(run, campaign, vehicle) for run, campaign, vehicle in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/mutation-executions/{execution_id}", response_model=MutationExecutionResponse)
async def get_execution_endpoint(
    execution_id: Annotated[str, slug_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> MutationExecutionResponse:
    execution, campaign, vehicle = await require_execution(session, execution_id)
    return execution_response(execution, campaign, vehicle)


@router.get("/mutation-executions/{execution_id}/mutants", response_model=MutantResultPage)
async def list_results_endpoint(
    execution_id: Annotated[str, slug_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> MutantResultPage:
    execution, _campaign, _vehicle = await require_execution(session, execution_id)
    results, total = await list_results(session, execution=execution, limit=limit, offset=offset)
    return MutantResultPage(
        items=[result_response(item, execution.execution_id) for item in results],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/mutation-executions/{execution_id}/mutants/{mutant_id}",
    response_model=MutantResultResponse,
)
async def update_result_endpoint(
    execution_id: Annotated[str, slug_path],
    mutant_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")],
    command: MutantResultUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> MutantResultResponse:
    execution, campaign, vehicle = await require_execution(session, execution_id, for_update=True)
    result = await require_result(
        session, execution=execution, mutant_id=mutant_id, for_update=True
    )
    result, _ = await update_result(
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
    return result_response(result, execution.execution_id)


@router.put(
    "/requirement-coverage/{requirement_id}",
    response_model=RequirementCoverageResponse,
    status_code=201,
)
async def upsert_coverage_endpoint(
    requirement_id: Annotated[str, Path(pattern=r"^[A-Z][A-Z0-9-]{2,79}$")],
    command: RequirementCoverageUpsert,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> RequirementCoverageResponse:
    item, duplicate = await upsert_requirement_coverage(
        session,
        requirement_id=requirement_id,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate or item.version > 1:
        response.status_code = status.HTTP_200_OK
    return coverage_response(item)


@router.get("/requirement-coverage", response_model=RequirementCoveragePage)
async def list_coverage_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[CoverageStatus | None, Query(alias="status")] = None,
) -> RequirementCoveragePage:
    items, total, counts = await list_coverage(
        session, limit=limit, offset=offset, status=status_filter
    )
    return RequirementCoveragePage(
        items=[coverage_response(item) for item in items],
        total=total,
        gaps=counts[CoverageStatus.GAP.value],
        partial=counts[CoverageStatus.PARTIAL.value],
        covered=counts[CoverageStatus.COVERED.value],
        limit=limit,
        offset=offset,
    )


@router.get("/requirement-coverage/{requirement_id}", response_model=RequirementCoverageResponse)
async def get_coverage_endpoint(
    requirement_id: Annotated[str, Path(pattern=r"^[A-Z][A-Z0-9-]{2,79}$")],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> RequirementCoverageResponse:
    return coverage_response(await require_coverage(session, requirement_id))
