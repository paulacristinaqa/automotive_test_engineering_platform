from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings, get_settings
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.registry.models import ModuleCapability, PlatformModule
from atep.registry.schemas import (
    CAPABILITY_NAME_PATTERN,
    CapabilityResponse,
    CapabilityUpdate,
    ModuleCreate,
    ModuleCredentialCommand,
    ModuleCredentialResponse,
    ModuleHealthSummary,
    ModuleHeartbeat,
    ModulePage,
    ModuleResponse,
    ModuleStatus,
    ModuleUpdate,
)
from atep.registry.service import (
    create_module,
    declare_capability,
    heartbeat_module,
    issue_module_credential,
    list_modules,
    remove_capability,
    require_module,
    summarize_module_health,
    update_module,
)

router = APIRouter(prefix="/modules", tags=["modules"])
modules_read = require_permissions(PermissionName.MODULES_READ.value)
modules_manage = require_permissions(PermissionName.MODULES_MANAGE.value)


def capability_response(capability: ModuleCapability) -> CapabilityResponse:
    return CapabilityResponse(
        id=capability.id,
        name=capability.name,
        version=capability.version,
        description=capability.description,
        created_at=capability.created_at,
        updated_at=capability.updated_at,
    )


def module_response(module: PlatformModule) -> ModuleResponse:
    return ModuleResponse(
        id=module.id,
        name=module.name,
        display_name=module.display_name,
        description=module.description,
        version=module.version,
        base_url=module.base_url,
        status=ModuleStatus(module.status),
        last_seen_at=module.last_seen_at,
        lease_expires_at=module.lease_expires_at,
        lease_duration_seconds=module.lease_duration_seconds,
        capabilities=[capability_response(item) for item in module.capabilities],
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


@router.post("", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_module_endpoint(
    command: ModuleCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(modules_manage)],
) -> ModuleResponse:
    module = await create_module(
        session,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return module_response(module)


@router.post("/{module_id}/credentials", response_model=ModuleCredentialResponse)
async def issue_module_credential_endpoint(
    module_id: UUID,
    command: ModuleCredentialCommand,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(modules_manage)],
) -> ModuleCredentialResponse:
    module, token = await issue_module_credential(
        session,
        module_id=module_id,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return ModuleCredentialResponse(
        module_id=module.id,
        module_token=token,
        lease_duration_seconds=module.lease_duration_seconds,
    )


@router.post("/{module_id}/heartbeat", response_model=ModuleResponse)
async def heartbeat_module_endpoint(
    module_id: UUID,
    command: ModuleHeartbeat,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    module_token: Annotated[str, Header(alias="X-ATEP-Module-Token", min_length=32)],
) -> ModuleResponse:
    module = await heartbeat_module(
        session,
        module_id=module_id,
        token=module_token,
        command=command,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    request.app.state.observability.module_heartbeats.labels(module.status).inc()
    return module_response(module)


@router.get("", response_model=ModulePage)
async def list_modules_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(modules_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    status_filter: Annotated[ModuleStatus | None, Query(alias="status")] = None,
    capability: Annotated[str | None, Query(min_length=3, max_length=120)] = None,
) -> ModulePage:
    modules, total = await list_modules(
        session,
        limit=limit,
        offset=offset,
        status=status_filter,
        capability=capability,
    )
    return ModulePage(
        items=[module_response(item) for item in modules],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/health-summary", response_model=ModuleHealthSummary)
async def module_health_summary_endpoint(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(modules_read)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModuleHealthSummary:
    summary = await summarize_module_health(
        session,
        availability_target=settings.module_availability_slo_target,
        lease_warning_seconds=settings.module_lease_warning_seconds,
    )
    request.app.state.observability.update_module_health(
        counts=summary.counts.model_dump(),
        monitored_modules=summary.monitored_modules,
        availability_ratio=summary.availability_ratio,
        at_risk_leases=summary.at_risk_leases,
    )
    return summary


@router.get("/{module_id}", response_model=ModuleResponse)
async def get_module_endpoint(
    module_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(modules_read)],
) -> ModuleResponse:
    return module_response(await require_module(session, module_id))


@router.patch("/{module_id}", response_model=ModuleResponse)
async def update_module_endpoint(
    module_id: UUID,
    command: ModuleUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(modules_manage)],
) -> ModuleResponse:
    module = await update_module(
        session,
        module_id=module_id,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return module_response(module)


@router.put("/{module_id}/capabilities/{capability_name}", response_model=ModuleResponse)
async def declare_capability_endpoint(
    module_id: UUID,
    capability_name: Annotated[
        str, Path(min_length=3, max_length=120, pattern=CAPABILITY_NAME_PATTERN.pattern)
    ],
    command: CapabilityUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(modules_manage)],
) -> ModuleResponse:
    module = await declare_capability(
        session,
        module_id=module_id,
        capability_name=capability_name,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return module_response(module)


@router.delete("/{module_id}/capabilities/{capability_name}", response_model=ModuleResponse)
async def remove_capability_endpoint(
    module_id: UUID,
    capability_name: Annotated[
        str, Path(min_length=3, max_length=120, pattern=CAPABILITY_NAME_PATTERN.pattern)
    ],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(modules_manage)],
) -> ModuleResponse:
    module = await remove_capability(
        session,
        module_id=module_id,
        capability_name=capability_name,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return module_response(module)
