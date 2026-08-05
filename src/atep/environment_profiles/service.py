from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    EnvironmentProfileConflictError,
    EnvironmentProfileStateError,
    EnvironmentProfileVersionConflictError,
    ResourceNotFoundError,
)
from atep.environment_profiles.models import EnvironmentProfile
from atep.environment_profiles.schemas import (
    EnvironmentProfileCreate,
    EnvironmentProfileStatus,
    EnvironmentProfileStatusUpdate,
)
from atep.events.outbox import enqueue_event

ALLOWED_STATUS_TRANSITIONS = {
    EnvironmentProfileStatus.DRAFT: {EnvironmentProfileStatus.ACTIVE},
    EnvironmentProfileStatus.ACTIVE: {EnvironmentProfileStatus.ARCHIVED},
    EnvironmentProfileStatus.ARCHIVED: set(),
}


async def create_environment_profile(
    session: AsyncSession,
    *,
    command: EnvironmentProfileCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EnvironmentProfile, bool]:
    existing = await session.scalar(
        select(EnvironmentProfile).where(EnvironmentProfile.profile_id == command.profile_id)
    )
    if existing is not None:
        if not _same_creation(existing, command, actor_user_id):
            raise EnvironmentProfileConflictError()
        return existing, True

    profile = EnvironmentProfile(
        profile_id=command.profile_id,
        created_by_user_id=actor_user_id,
        name=command.name,
        description=command.description,
        vehicle_kind=command.vehicle_kind.value,
        property_source=command.property_source.value,
        configuration=command.configuration,
        status=EnvironmentProfileStatus.DRAFT.value,
        version=1,
    )
    try:
        async with session.begin_nested():
            session.add(profile)
            await session.flush()
    except IntegrityError as exc:
        raise EnvironmentProfileConflictError() from exc
    payload = environment_profile_payload(profile)
    enqueue_event(
        session,
        event_type="atep.environment_profile.created.v1",
        aggregate_type="environment_profile",
        aggregate_id=profile.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="environment_profile.created",
        resource_type="environment_profile",
        resource_id=profile.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return profile, False


async def require_environment_profile(
    session: AsyncSession, profile_id: str, *, for_update: bool = False
) -> EnvironmentProfile:
    query = select(EnvironmentProfile).where(EnvironmentProfile.profile_id == profile_id)
    if for_update:
        query = query.with_for_update()
    profile = await session.scalar(query)
    if profile is None:
        raise ResourceNotFoundError("environment_profile")
    return profile


async def require_active_environment_profile(
    session: AsyncSession, profile_id: str
) -> EnvironmentProfile:
    profile = await require_environment_profile(session, profile_id)
    if profile.status != EnvironmentProfileStatus.ACTIVE.value:
        raise EnvironmentProfileStateError(
            current_status=profile.status, requested_status="use_in_test_run"
        )
    return profile


async def list_environment_profiles(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: EnvironmentProfileStatus | None = None,
) -> tuple[list[EnvironmentProfile], int]:
    query = select(EnvironmentProfile)
    if status is not None:
        query = query.where(EnvironmentProfile.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(EnvironmentProfile.profile_id, EnvironmentProfile.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def update_environment_profile_status(
    session: AsyncSession,
    *,
    profile: EnvironmentProfile,
    command: EnvironmentProfileStatusUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EnvironmentProfile, bool]:
    if profile.status == command.status.value:
        return profile, True
    if profile.version != command.expected_version:
        raise EnvironmentProfileVersionConflictError(current_version=profile.version)
    current = EnvironmentProfileStatus(profile.status)
    if command.status not in ALLOWED_STATUS_TRANSITIONS[current]:
        raise EnvironmentProfileStateError(
            current_status=current.value, requested_status=command.status.value
        )
    previous_status = profile.status
    profile.status = command.status.value
    profile.version += 1
    await session.flush()
    await session.refresh(profile, attribute_names=["updated_at"])
    payload = {**environment_profile_payload(profile), "previous_status": previous_status}
    enqueue_event(
        session,
        event_type="atep.environment_profile.status_changed.v1",
        aggregate_type="environment_profile",
        aggregate_id=profile.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="environment_profile.status_changed",
        resource_type="environment_profile",
        resource_id=profile.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return profile, False


def environment_profile_payload(profile: EnvironmentProfile) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "created_by_user_id": str(profile.created_by_user_id),
        "name": profile.name,
        "description": profile.description,
        "vehicle_kind": profile.vehicle_kind,
        "property_source": profile.property_source,
        "configuration": profile.configuration,
        "status": profile.status,
        "version": profile.version,
    }


def _same_creation(
    profile: EnvironmentProfile, command: EnvironmentProfileCreate, actor_user_id: UUID
) -> bool:
    return (
        profile.created_by_user_id == actor_user_id
        and profile.name == command.name
        and profile.description == command.description
        and profile.vehicle_kind == command.vehicle_kind.value
        and profile.property_source == command.property_source.value
        and profile.configuration == command.configuration
    )
