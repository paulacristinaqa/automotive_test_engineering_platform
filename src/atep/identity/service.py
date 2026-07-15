from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import DuplicateEmailError, ResourceNotFoundError
from atep.core.security import DUMMY_HASH, hash_password, verify_password
from atep.events.outbox import enqueue_event
from atep.identity.models import Role, User
from atep.identity.schemas import UserCreate


def normalize_email(email: str) -> str:
    return email.strip().casefold()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == normalize_email(email)))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email)
    encoded_hash = user.password_hash if user is not None else DUMMY_HASH
    password_matches = verify_password(password, encoded_hash)
    if user is None or not password_matches or not user.is_active:
        return None
    return user


async def list_users(session: AsyncSession, *, limit: int, offset: int) -> tuple[list[User], int]:
    total = await session.scalar(select(func.count()).select_from(User))
    result = await session.execute(
        select(User).order_by(User.email, User.id).limit(limit).offset(offset)
    )
    return list(result.scalars().unique().all()), int(total or 0)


async def require_user(session: AsyncSession, user_id: UUID) -> User:
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise ResourceNotFoundError("user")
    return user


async def create_user(
    session: AsyncSession,
    *,
    command: UserCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> User:
    email = normalize_email(str(command.email))
    if await get_user_by_email(session, email) is not None:
        raise DuplicateEmailError()

    user = User(
        email=email,
        display_name=command.display_name.strip(),
        password_hash=hash_password(command.password.get_secret_value()),
        is_active=True,
        roles=[],
    )
    try:
        async with session.begin_nested():
            session.add(user)
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateEmailError() from exc

    enqueue_event(
        session,
        event_type="atep.identity.user.created.v1",
        aggregate_type="user",
        aggregate_id=user.id,
        correlation_id=correlation_id,
        payload={"user_id": str(user.id), "email": user.email, "bootstrap": False},
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="identity.user.created",
        resource_type="user",
        resource_id=user.id,
        correlation_id=correlation_id,
        details={"email": user.email},
    )
    return user


async def set_user_status(
    session: AsyncSession,
    *,
    user_id: UUID,
    is_active: bool,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> User:
    user = await require_user(session, user_id)
    previous = user.is_active
    user.is_active = is_active
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="identity.user.status_changed",
        resource_type="user",
        resource_id=user.id,
        correlation_id=correlation_id,
        details={"previous": previous, "current": is_active},
    )
    return user


async def assign_role(
    session: AsyncSession,
    *,
    user_id: UUID,
    role_id: UUID,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> User:
    user = await require_user(session, user_id)
    role = await session.get(Role, role_id)
    if role is None:
        raise ResourceNotFoundError("role")
    if all(existing.id != role.id for existing in user.roles):
        user.roles.append(role)
        record_audit(
            session,
            actor_user_id=actor_user_id,
            action="identity.user.role_assigned",
            resource_type="user",
            resource_id=user.id,
            correlation_id=correlation_id,
            details={"role_id": str(role.id), "role": role.name},
        )
    return user


async def remove_role(
    session: AsyncSession,
    *,
    user_id: UUID,
    role_id: UUID,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> User:
    user = await require_user(session, user_id)
    role = next((item for item in user.roles if item.id == role_id), None)
    if role is None:
        raise ResourceNotFoundError("role_assignment")
    user.roles.remove(role)
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="identity.user.role_removed",
        resource_type="user",
        resource_id=user.id,
        correlation_id=correlation_id,
        details={"role_id": str(role.id), "role": role.name},
    )
    return user
