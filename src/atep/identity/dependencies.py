from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings, get_settings
from atep.core.security import InvalidTokenError, decode_access_token
from atep.db.session import get_session
from atep.identity.models import User
from atep.identity.service import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


async def current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_credentials", "message": "Authentication is required."},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token, settings)
    except InvalidTokenError as exc:
        raise unauthorized from exc
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_permissions(*required: str) -> Callable[..., Awaitable[User]]:
    async def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        missing = set(required) - user.permission_names
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "permission_denied", "message": "Permission denied."},
            )
        return user

    return dependency
