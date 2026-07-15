import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from atep.core.config import Settings

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("not-a-real-password")


class InvalidTokenError(ValueError):
    """Raised when an access token cannot be trusted."""


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_module_token() -> str:
    return secrets.token_urlsafe(48)


def hash_module_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_module_token(token: str, encoded_hash: str) -> bool:
    return secrets.compare_digest(hash_module_token(token), encoded_hash)


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def create_access_token(user_id: UUID, settings: Settings, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_minutes),
        "iss": "atep-core",
        "type": "access",
    }
    return jwt.encode(
        claims, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer="atep-core",
        )
        if claims.get("type") != "access":
            raise InvalidTokenError("unexpected token type")
        return UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("invalid access token") from exc
