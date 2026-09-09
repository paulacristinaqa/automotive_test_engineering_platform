from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.errors import ResourceNotFoundError
from atep.cross_platform_automation.schemas import (
    AutomationOutcome,
    AutomationReportCreate,
    AutomationReportPage,
    AutomationReportResponse,
)
from atep.cross_platform_automation.service import (
    create_report,
    list_reports,
    report_response,
    require_report,
)
from atep.db.session import get_session
from atep.fault_campaigns.models import FaultCampaignExecution
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.mutation_analysis.models import MutationExecution
from atep.registry.models import PlatformModule
from atep.test_runs.service import require_test_run
from atep.vehicles.models import VehicleCommand, VehicleTelemetryEvent
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/cross-platform-automation", tags=["cross-platform-automation"])
read_access = require_permissions(PermissionName.TEST_CATALOG_READ.value)
manage_access = require_permissions(PermissionName.TEST_CATALOG_MANAGE.value)
report_path = Path(pattern=r"^[a-z0-9][a-z0-9-]{7,63}$")


@router.post("/reports", response_model=AutomationReportResponse, status_code=201)
async def create_report_endpoint(
    command: AutomationReportCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(manage_access)],
) -> AutomationReportResponse:
    vehicle = await require_vehicle(session, command.vehicle_id)
    test_run, _ = await require_test_run(session, command.test_run_id)
    gateway = await session.get(PlatformModule, command.gateway_module_id)
    if gateway is None:
        raise ResourceNotFoundError("platform_module")
    telemetry_events = list(
        await session.scalars(
            select(VehicleTelemetryEvent).where(
                VehicleTelemetryEvent.event_id.in_(command.telemetry_event_ids)
            )
        )
    )
    vehicle_commands = list(
        await session.scalars(
            select(VehicleCommand).where(VehicleCommand.command_id.in_(command.vehicle_command_ids))
        )
    )
    fault_execution = None
    if command.fault_execution_id is not None:
        fault_execution = await session.scalar(
            select(FaultCampaignExecution).where(
                FaultCampaignExecution.execution_id == command.fault_execution_id
            )
        )
    mutation_execution = None
    if command.mutation_execution_id is not None:
        mutation_execution = await session.scalar(
            select(MutationExecution).where(
                MutationExecution.execution_id == command.mutation_execution_id
            )
        )
    report, duplicate = await create_report(
        session,
        command=command,
        vehicle=vehicle,
        test_run=test_run,
        gateway=gateway,
        telemetry_events=telemetry_events,
        vehicle_commands=vehicle_commands,
        fault_execution=fault_execution,
        mutation_execution=mutation_execution,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return report_response(
        report,
        vehicle=vehicle,
        test_run=test_run,
        fault_execution=fault_execution,
        mutation_execution=mutation_execution,
        duplicate=duplicate,
    )


@router.get("/reports", response_model=AutomationReportPage)
async def list_reports_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    outcome: AutomationOutcome | None = None,
) -> AutomationReportPage:
    rows, total = await list_reports(session, limit=limit, offset=offset, outcome=outcome)
    return AutomationReportPage(
        items=[
            report_response(
                report,
                vehicle=vehicle,
                test_run=test_run,
                fault_execution=fault_execution,
                mutation_execution=mutation_execution,
            )
            for report, vehicle, test_run, fault_execution, mutation_execution in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/reports/{report_id}", response_model=AutomationReportResponse)
async def get_report_endpoint(
    report_id: Annotated[str, report_path],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(read_access)],
) -> AutomationReportResponse:
    report, vehicle, test_run, fault_execution, mutation_execution = await require_report(
        session, report_id
    )
    return report_response(
        report,
        vehicle=vehicle,
        test_run=test_run,
        fault_execution=fault_execution,
        mutation_execution=mutation_execution,
    )
