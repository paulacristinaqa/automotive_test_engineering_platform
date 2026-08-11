from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateModuleNameError,
    InvalidModuleCredentialError,
    ModuleCapabilityRequiredError,
    ResourceNotFoundError,
)
from atep.core.security import generate_module_token, hash_module_token, verify_module_token
from atep.events.outbox import enqueue_event
from atep.registry.models import ModuleCapability, PlatformModule
from atep.registry.schemas import (
    CapabilityUpdate,
    ModuleCreate,
    ModuleCredentialCommand,
    ModuleHealthStatus,
    ModuleHealthSummary,
    ModuleHeartbeat,
    ModuleStatus,
    ModuleStatusCounts,
    ModuleUpdate,
    normalize_capability_name,
)


def _valid_module_authentication(
    module: PlatformModule,
    *,
    token: str | None,
    spiffe_module_name: str | None,
) -> bool:
    if spiffe_module_name is not None:
        return module.name == spiffe_module_name
    return (
        token is not None
        and module.heartbeat_token_hash is not None
        and verify_module_token(token, module.heartbeat_token_hash)
    )


async def summarize_module_health(
    session: AsyncSession,
    *,
    availability_target: float,
    lease_warning_seconds: int,
    now: datetime | None = None,
) -> ModuleHealthSummary:
    observed_at = now or datetime.now(UTC)
    monitored = PlatformModule.heartbeat_token_hash.is_not(None)
    at_risk = (
        monitored
        & PlatformModule.status.in_([ModuleStatus.ACTIVE.value, ModuleStatus.DEGRADED.value])
        & PlatformModule.lease_expires_at.is_not(None)
        & (
            PlatformModule.lease_expires_at
            <= observed_at + timedelta(seconds=lease_warning_seconds)
        )
    )
    result = await session.execute(
        select(
            func.count().filter(monitored),
            func.count().filter(
                monitored & (PlatformModule.status == ModuleStatus.REGISTERED.value)
            ),
            func.count().filter(monitored & (PlatformModule.status == ModuleStatus.ACTIVE.value)),
            func.count().filter(monitored & (PlatformModule.status == ModuleStatus.DEGRADED.value)),
            func.count().filter(monitored & (PlatformModule.status == ModuleStatus.INACTIVE.value)),
            func.count().filter(at_risk),
        )
    )
    monitored_count, registered, active, degraded, inactive, at_risk_leases = result.one()
    counts = ModuleStatusCounts(
        registered=int(registered),
        active=int(active),
        degraded=int(degraded),
        inactive=int(inactive),
    )
    monitored_count = int(monitored_count)
    availability_ratio = active / monitored_count if monitored_count else None
    objective_met = (
        availability_ratio >= availability_target if availability_ratio is not None else None
    )
    if monitored_count == 0:
        health_status = ModuleHealthStatus.UNMONITORED
    elif active == 0:
        health_status = ModuleHealthStatus.UNAVAILABLE
    elif objective_met and degraded == 0 and inactive == 0 and registered == 0:
        health_status = ModuleHealthStatus.HEALTHY
    else:
        health_status = ModuleHealthStatus.DEGRADED
    return ModuleHealthSummary(
        generated_at=observed_at,
        status=health_status,
        availability_target=availability_target,
        availability_ratio=availability_ratio,
        objective_met=objective_met,
        monitored_modules=monitored_count,
        at_risk_leases=int(at_risk_leases),
        counts=counts,
    )


async def list_modules(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: ModuleStatus | None = None,
    capability: str | None = None,
) -> tuple[list[PlatformModule], int]:
    query = select(PlatformModule)
    if status is not None:
        query = query.where(PlatformModule.status == status.value)
    if capability is not None:
        normalized = normalize_capability_name(capability)
        query = query.where(PlatformModule.capabilities.any(ModuleCapability.name == normalized))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(PlatformModule.name, PlatformModule.id).limit(limit).offset(offset)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def require_module(session: AsyncSession, module_id: UUID) -> PlatformModule:
    module = await session.get(PlatformModule, module_id)
    if module is None:
        raise ResourceNotFoundError("module")
    return module


async def authenticate_module(
    session: AsyncSession,
    *,
    module_id: UUID,
    token: str | None,
    spiffe_module_name: str | None = None,
    required_capability: str | None = None,
) -> PlatformModule:
    module = await require_module(session, module_id)
    if not _valid_module_authentication(module, token=token, spiffe_module_name=spiffe_module_name):
        raise InvalidModuleCredentialError()
    if required_capability is not None and required_capability not in {
        item.name for item in module.capabilities
    }:
        raise ModuleCapabilityRequiredError(required_capability)
    return module


async def create_module(
    session: AsyncSession,
    *,
    command: ModuleCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> PlatformModule:
    existing = await session.scalar(
        select(PlatformModule).where(PlatformModule.name == command.name)
    )
    if existing is not None:
        raise DuplicateModuleNameError()
    module = PlatformModule(
        name=command.name,
        display_name=command.display_name,
        description=command.description,
        version=command.version,
        base_url=str(command.base_url) if command.base_url is not None else None,
        status=ModuleStatus.REGISTERED.value,
        capabilities=[
            ModuleCapability(
                name=item.name,
                version=item.version,
                description=item.description,
            )
            for item in command.capabilities
        ],
    )
    try:
        async with session.begin_nested():
            session.add(module)
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateModuleNameError() from exc
    payload = _module_event_payload(module)
    enqueue_event(
        session,
        event_type="atep.platform.module.registered.v1",
        aggregate_type="platform_module",
        aggregate_id=module.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="platform.module.registered",
        resource_type="platform_module",
        resource_id=module.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return module


async def update_module(
    session: AsyncSession,
    *,
    module_id: UUID,
    command: ModuleUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> PlatformModule:
    module = await require_module(session, module_id)
    previous = {
        "display_name": module.display_name,
        "description": module.description,
        "version": module.version,
        "base_url": module.base_url,
        "status": module.status,
    }
    changes = command.model_dump(exclude_unset=True)
    if "base_url" in changes:
        changes["base_url"] = str(command.base_url) if command.base_url is not None else None
    if command.status is not None:
        changes["status"] = command.status.value
    for field, value in changes.items():
        setattr(module, field, value)
    await session.flush()
    await session.refresh(module, attribute_names=["updated_at"])
    details = {"previous": previous, "current": _module_metadata(module)}
    enqueue_event(
        session,
        event_type="atep.platform.module.updated.v1",
        aggregate_type="platform_module",
        aggregate_id=module.id,
        payload=_module_event_payload(module),
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="platform.module.updated",
        resource_type="platform_module",
        resource_id=module.id,
        correlation_id=correlation_id,
        details=details,
    )
    return module


async def issue_module_credential(
    session: AsyncSession,
    *,
    module_id: UUID,
    command: ModuleCredentialCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[PlatformModule, str]:
    module = await require_module(session, module_id)
    token = generate_module_token()
    module.heartbeat_token_hash = hash_module_token(token)
    module.lease_duration_seconds = command.lease_duration_seconds
    module.lease_expires_at = None
    module.last_seen_at = None
    if module.status in {ModuleStatus.ACTIVE.value, ModuleStatus.DEGRADED.value}:
        module.status = ModuleStatus.REGISTERED.value
    await session.flush()
    details = {
        "module_name": module.name,
        "lease_duration_seconds": module.lease_duration_seconds,
    }
    enqueue_event(
        session,
        event_type="atep.platform.module.credential-rotated.v1",
        aggregate_type="platform_module",
        aggregate_id=module.id,
        payload={"module_id": str(module.id), **details},
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="platform.module.credential_rotated",
        resource_type="platform_module",
        resource_id=module.id,
        correlation_id=correlation_id,
        details=details,
    )
    return module, token


async def heartbeat_module(
    session: AsyncSession,
    *,
    module_id: UUID,
    token: str | None,
    spiffe_module_name: str | None = None,
    command: ModuleHeartbeat,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> PlatformModule:
    result = await session.execute(
        select(PlatformModule).where(PlatformModule.id == module_id).with_for_update()
    )
    module = result.scalar_one_or_none()
    if module is None:
        raise ResourceNotFoundError("module")
    if not _valid_module_authentication(module, token=token, spiffe_module_name=spiffe_module_name):
        raise InvalidModuleCredentialError()

    observed_at = now or datetime.now(UTC)
    previous_status = module.status
    previous_version = module.version
    module.last_seen_at = observed_at
    module.lease_expires_at = observed_at + timedelta(seconds=module.lease_duration_seconds)
    module.status = command.status.value
    if command.version is not None:
        module.version = command.version
    await session.flush()
    await session.refresh(module, attribute_names=["updated_at"])

    if module.status != previous_status or module.version != previous_version:
        enqueue_event(
            session,
            event_type="atep.platform.module.availability-changed.v1",
            aggregate_type="platform_module",
            aggregate_id=module.id,
            payload={
                "module_id": str(module.id),
                "module_name": module.name,
                "previous_status": previous_status,
                "status": module.status,
                "previous_version": previous_version,
                "version": module.version,
                "observed_at": observed_at.isoformat(),
                "lease_expires_at": module.lease_expires_at.isoformat(),
                "reason": "heartbeat",
            },
            correlation_id=correlation_id,
        )
    return module


async def reconcile_expired_modules(session: AsyncSession, *, now: datetime | None = None) -> int:
    observed_at = now or datetime.now(UTC)
    result = await session.execute(
        select(PlatformModule)
        .where(
            PlatformModule.status.in_([ModuleStatus.ACTIVE.value, ModuleStatus.DEGRADED.value]),
            PlatformModule.lease_expires_at.is_not(None),
            PlatformModule.lease_expires_at <= observed_at,
        )
        .with_for_update(skip_locked=True)
    )
    modules = list(result.scalars().all())
    for module in modules:
        previous_status = module.status
        module.status = ModuleStatus.INACTIVE.value
        details = {
            "module_name": module.name,
            "previous_status": previous_status,
            "status": module.status,
            "lease_expires_at": (
                module.lease_expires_at.isoformat() if module.lease_expires_at else None
            ),
            "observed_at": observed_at.isoformat(),
            "reason": "lease_expired",
        }
        enqueue_event(
            session,
            event_type="atep.platform.module.availability-changed.v1",
            aggregate_type="platform_module",
            aggregate_id=module.id,
            payload={"module_id": str(module.id), **details},
        )
        record_audit(
            session,
            actor_user_id=None,
            action="platform.module.lease_expired",
            resource_type="platform_module",
            resource_id=module.id,
            correlation_id=None,
            details=details,
        )
    await session.flush()
    return len(modules)


async def declare_capability(
    session: AsyncSession,
    *,
    module_id: UUID,
    capability_name: str,
    command: CapabilityUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> PlatformModule:
    module = await require_module(session, module_id)
    normalized_name = normalize_capability_name(capability_name)
    capability = next((item for item in module.capabilities if item.name == normalized_name), None)
    action = "declared"
    if capability is None:
        capability = ModuleCapability(
            name=normalized_name,
            version=command.version,
            description=command.description,
        )
        module.capabilities.append(capability)
    else:
        capability.version = command.version
        capability.description = command.description
        action = "updated"
    await session.flush()
    capability_details = {
        "name": capability.name,
        "version": capability.version,
        "description": capability.description,
    }
    event_payload = {
        "module_id": str(module.id),
        "module_name": module.name,
        "capability": capability_details,
    }
    enqueue_event(
        session,
        event_type=f"atep.platform.module.capability-{action}.v1",
        aggregate_type="platform_module",
        aggregate_id=module.id,
        payload=event_payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action=f"platform.module.capability_{action}",
        resource_type="platform_module",
        resource_id=module.id,
        correlation_id=correlation_id,
        details=capability_details,
    )
    return module


async def remove_capability(
    session: AsyncSession,
    *,
    module_id: UUID,
    capability_name: str,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> PlatformModule:
    module = await require_module(session, module_id)
    normalized_name = normalize_capability_name(capability_name)
    capability = next((item for item in module.capabilities if item.name == normalized_name), None)
    if capability is None:
        raise ResourceNotFoundError("capability")
    details = {
        "name": capability.name,
        "version": capability.version,
        "description": capability.description,
    }
    module.capabilities.remove(capability)
    enqueue_event(
        session,
        event_type="atep.platform.module.capability-removed.v1",
        aggregate_type="platform_module",
        aggregate_id=module.id,
        payload={"module_id": str(module.id), "module_name": module.name, "capability": details},
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="platform.module.capability_removed",
        resource_type="platform_module",
        resource_id=module.id,
        correlation_id=correlation_id,
        details=details,
    )
    return module


def _module_metadata(module: PlatformModule) -> dict[str, str | None]:
    return {
        "display_name": module.display_name,
        "description": module.description,
        "version": module.version,
        "base_url": module.base_url,
        "status": module.status,
    }


def _module_event_payload(module: PlatformModule) -> dict[str, object]:
    return {
        "module_id": str(module.id),
        "name": module.name,
        **_module_metadata(module),
        "capabilities": [
            {"name": item.name, "version": item.version} for item in module.capabilities
        ],
    }
