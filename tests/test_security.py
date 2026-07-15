from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings
from atep.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from atep.identity.dependencies import current_user
from atep.identity.models import User


def settings() -> Settings:
    return Settings(jwt_secret="test-secret-that-is-longer-than-32-characters")


def test_password_is_hashed_and_verified() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("incorrect password", encoded)


def test_short_password_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 12"):
        hash_password("too-short")


def test_refresh_tokens_are_random_and_only_compared_by_hash() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()
    assert first != second
    assert len(first) >= 64
    assert hash_refresh_token(first) == hash_refresh_token(first)
    assert hash_refresh_token(first) != hash_refresh_token(second)
    assert first not in hash_refresh_token(first)


def test_bootstrap_administrator_requires_deliverable_email() -> None:
    with pytest.raises(ValidationError):
        Settings(
            jwt_secret="test-secret-that-is-longer-than-32-characters",
            bootstrap_admin_email="admin@atep.local",
        )


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    token = create_access_token(user_id, settings(), now=datetime.now(UTC))
    assert decode_access_token(token, settings()) == user_id


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(uuid4(), settings(), now=datetime.now(UTC))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token + "tampered", settings())


class InactiveUserSession:
    def __init__(self, user: User) -> None:
        self.user = user

    async def get(self, _: type[User], __: object) -> User:
        return self.user


@pytest.mark.asyncio
async def test_disabled_user_loses_access_even_with_valid_unexpired_token() -> None:
    user = User(
        id=uuid4(),
        email="disabled@example.com",
        display_name="Disabled",
        password_hash="unused",
        is_active=False,
        roles=[],
    )
    token = create_access_token(user.id, settings())
    with pytest.raises(HTTPException) as captured:
        await current_user(token, cast(AsyncSession, InactiveUserSession(user)), settings())
    assert captured.value.status_code == 401
