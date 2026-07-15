from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.config import Settings
from atep.core.errors import InvalidRefreshTokenError
from atep.core.security import create_access_token, generate_refresh_token, hash_refresh_token
from atep.identity.models import RefreshToken, User


@dataclass(frozen=True, slots=True)
class SessionTokenPair:
    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int


async def issue_session_tokens(
    session: AsyncSession,
    *,
    user: User,
    settings: Settings,
    family_id: UUID | None = None,
    now: datetime | None = None,
) -> tuple[SessionTokenPair, RefreshToken]:
    issued_at = now or datetime.now(UTC)
    raw_refresh_token = generate_refresh_token()
    refresh_lifetime = timedelta(days=settings.refresh_token_days)
    refresh = RefreshToken(
        user_id=user.id,
        family_id=family_id or uuid4(),
        token_hash=hash_refresh_token(raw_refresh_token),
        expires_at=issued_at + refresh_lifetime,
        used_at=None,
        revoked_at=None,
        replaced_by_id=None,
        revocation_reason=None,
    )
    session.add(refresh)
    await session.flush()
    return (
        SessionTokenPair(
            access_token=create_access_token(user.id, settings, now=issued_at),
            refresh_token=raw_refresh_token,
            access_expires_in=settings.access_token_minutes * 60,
            refresh_expires_in=int(refresh_lifetime.total_seconds()),
        ),
        refresh,
    )


async def _refresh_by_value(session: AsyncSession, raw_refresh_token: str) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw_refresh_token))
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _revoke_family(
    session: AsyncSession,
    *,
    family_id: UUID,
    revoked_at: datetime,
    reason: str,
) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=revoked_at, revocation_reason=reason)
    )


async def rotate_session_tokens(
    session: AsyncSession,
    *,
    raw_refresh_token: str,
    settings: Settings,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> SessionTokenPair:
    rotated_at = now or datetime.now(UTC)
    current = await _refresh_by_value(session, raw_refresh_token)
    if current is None:
        raise InvalidRefreshTokenError()

    if current.used_at is not None or current.revoked_at is not None:
        await _revoke_family(
            session,
            family_id=current.family_id,
            revoked_at=rotated_at,
            reason="reuse_detected",
        )
        record_audit(
            session,
            actor_user_id=current.user_id,
            action="identity.session.reuse_detected",
            resource_type="refresh_token_family",
            resource_id=current.family_id,
            correlation_id=correlation_id,
        )
        await session.commit()
        raise InvalidRefreshTokenError()

    user = await session.get(User, current.user_id)
    if user is None or not user.is_active or current.expires_at <= rotated_at:
        current.revoked_at = rotated_at
        current.revocation_reason = "invalid_or_expired"
        await session.commit()
        raise InvalidRefreshTokenError()

    current.used_at = rotated_at
    pair, replacement = await issue_session_tokens(
        session,
        user=user,
        settings=settings,
        family_id=current.family_id,
        now=rotated_at,
    )
    current.replaced_by_id = replacement.id
    record_audit(
        session,
        actor_user_id=user.id,
        action="identity.session.rotated",
        resource_type="refresh_token",
        resource_id=current.id,
        correlation_id=correlation_id,
        details={"family_id": str(current.family_id)},
    )
    return pair


async def logout_session(
    session: AsyncSession,
    *,
    raw_refresh_token: str,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> None:
    revoked_at = now or datetime.now(UTC)
    current = await _refresh_by_value(session, raw_refresh_token)
    if current is None:
        return
    await _revoke_family(
        session,
        family_id=current.family_id,
        revoked_at=revoked_at,
        reason="logout",
    )
    record_audit(
        session,
        actor_user_id=current.user_id,
        action="identity.session.logged_out",
        resource_type="refresh_token_family",
        resource_id=current.family_id,
        correlation_id=correlation_id,
    )


async def logout_all_sessions(
    session: AsyncSession,
    *,
    user: User,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> None:
    revoked_at = now or datetime.now(UTC)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=revoked_at, revocation_reason="logout_all")
    )
    record_audit(
        session,
        actor_user_id=user.id,
        action="identity.session.logged_out_all",
        resource_type="user",
        resource_id=user.id,
        correlation_id=correlation_id,
    )
