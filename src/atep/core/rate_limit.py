import asyncio
import hashlib
import math
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Annotated, cast

import redis.asyncio as redis
from fastapi import Depends, Request, Response

from atep.core.config import Settings, get_settings
from atep.core.errors import RateLimitExceededError, RateLimitUnavailableError

_FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {count, ttl}
"""


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    limit: int
    remaining: int
    reset_after: int


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _client_identity(request: Request) -> str:
    authorization = request.headers.get("Authorization")
    if authorization:
        return f"credential:{_fingerprint(authorization)}"
    host = request.client.host if request.client is not None else "unknown"
    return f"client:{_fingerprint(host)}"


def _login_identities(request: Request, email: str) -> tuple[str, str]:
    host = request.client.host if request.client is not None else "unknown"
    normalized_email = email.strip().casefold()
    return (
        f"account:{_fingerprint(normalized_email)}",
        f"client:{_fingerprint(host)}",
    )


async def consume_rate_limit(
    client: redis.Redis,
    *,
    policy: RateLimitPolicy,
    identity: str,
) -> RateLimitResult:
    key = f"atep:rate-limit:{policy.name}:{identity}"
    try:
        async with asyncio.timeout(2):
            raw = cast(
                list[int | bytes],
                await cast(
                    Awaitable[str],
                    client.eval(
                        _FIXED_WINDOW_SCRIPT,
                        1,
                        key,
                        str(policy.window_seconds * 1_000),
                    ),
                ),
            )
    except Exception as exc:
        raise RateLimitUnavailableError from exc

    count, ttl_ms = (int(value) for value in raw)
    reset_after = max(1, math.ceil(ttl_ms / 1_000))
    remaining = max(0, policy.limit - count)
    result = RateLimitResult(
        limit=policy.limit,
        remaining=remaining,
        reset_after=reset_after,
    )
    if count > policy.limit:
        raise RateLimitExceededError(
            limit=result.limit,
            remaining=result.remaining,
            reset_after=result.reset_after,
        )
    return result


def apply_rate_limit_headers(response: Response, result: RateLimitResult) -> None:
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    response.headers["X-RateLimit-Reset"] = str(result.reset_after)


def redis_client(request: Request) -> redis.Redis:
    return cast(redis.Redis, request.app.state.redis)


async def api_rate_limit(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.rate_limit_enabled:
        return
    result = await consume_rate_limit(
        redis_client(request),
        policy=RateLimitPolicy(
            name="api",
            limit=settings.api_rate_limit_requests,
            window_seconds=settings.api_rate_limit_window_seconds,
        ),
        identity=_client_identity(request),
    )
    apply_rate_limit_headers(response, result)


async def authentication_rate_limit(
    request: Request,
    response: Response,
    *,
    email: str,
    settings: Settings,
) -> None:
    if not settings.rate_limit_enabled:
        return
    account_identity, client_identity = _login_identities(request, email)
    account_result = await consume_rate_limit(
        redis_client(request),
        policy=RateLimitPolicy(
            name="authentication-account",
            limit=settings.auth_rate_limit_requests,
            window_seconds=settings.auth_rate_limit_window_seconds,
        ),
        identity=account_identity,
    )
    client_result = await consume_rate_limit(
        redis_client(request),
        policy=RateLimitPolicy(
            name="authentication-client",
            limit=settings.auth_rate_limit_ip_requests,
            window_seconds=settings.auth_rate_limit_window_seconds,
        ),
        identity=client_identity,
    )
    tightest = min((account_result, client_result), key=lambda item: item.remaining)
    apply_rate_limit_headers(response, tightest)
