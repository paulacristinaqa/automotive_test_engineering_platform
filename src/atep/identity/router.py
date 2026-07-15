from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings, get_settings
from atep.core.rate_limit import authentication_rate_limit
from atep.db.session import get_session
from atep.identity.dependencies import current_user
from atep.identity.models import User
from atep.identity.schemas import RefreshTokenCommand, TokenResponse, UserResponse
from atep.identity.service import authenticate
from atep.identity.sessions import (
    SessionTokenPair,
    issue_session_tokens,
    logout_all_sessions,
    logout_session,
    rotate_session_tokens,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def request_correlation_id(request: Request) -> UUID | None:
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, UUID) else None


def token_response(pair: SessionTokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.access_expires_in,
        refresh_expires_in=pair.refresh_expires_in,
    )


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    await authentication_rate_limit(
        request,
        response,
        email=form.username,
        settings=settings,
    )
    user = await authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": "Invalid credentials."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    pair, _ = await issue_session_tokens(session, user=user, settings=settings)
    await session.commit()
    return token_response(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    command: RefreshTokenCommand,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    pair = await rotate_session_tokens(
        session,
        raw_refresh_token=command.refresh_token.get_secret_value(),
        settings=settings,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return token_response(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    command: RefreshTokenCommand,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await logout_session(
        session,
        raw_refresh_token=command.refresh_token.get_secret_value(),
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_user)],
) -> Response:
    await logout_all_sessions(
        session,
        user=user,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def read_current_user(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        roles=sorted(role.name for role in user.roles),
        permissions=sorted(user.permission_names),
    )
