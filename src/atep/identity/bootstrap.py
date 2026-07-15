from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings
from atep.core.security import hash_password
from atep.events.outbox import enqueue_event
from atep.identity.models import Permission, Role, User
from atep.identity.permissions import ADMIN_PERMISSIONS
from atep.identity.service import normalize_email


async def ensure_bootstrap_admin(session: AsyncSession, settings: Settings) -> bool:
    permissions: list[Permission] = []
    for name in ADMIN_PERMISSIONS:
        permission = await session.scalar(select(Permission).where(Permission.name == name.value))
        if permission is None:
            permission = Permission(name=name.value, description=f"Allows {name.value}")
            session.add(permission)
        permissions.append(permission)

    role = await session.scalar(select(Role).where(Role.name == "platform-admin"))
    if role is not None:
        existing_permission_names = {item.name for item in role.permissions}
        role.permissions.extend(
            item for item in permissions if item.name not in existing_permission_names
        )

    email = settings.bootstrap_admin_email
    password = settings.bootstrap_admin_password
    if email is None and password is None:
        return False
    if not email or password is None:
        raise RuntimeError("both bootstrap administrator variables must be configured")

    normalized_email = normalize_email(email)
    existing = await session.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        return False

    if role is None:
        role = Role(
            name="platform-admin",
            description="Full platform administration",
            permissions=permissions,
        )
        session.add(role)

    user = User(
        email=normalized_email,
        display_name="Platform Administrator",
        password_hash=hash_password(password.get_secret_value()),
        roles=[role],
    )
    session.add(user)
    await session.flush()
    enqueue_event(
        session,
        event_type="atep.identity.user.created.v1",
        aggregate_type="user",
        aggregate_id=user.id,
        payload={"user_id": str(user.id), "email": user.email, "bootstrap": True},
    )
    return True
