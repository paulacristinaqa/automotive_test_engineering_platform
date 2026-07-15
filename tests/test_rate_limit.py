from typing import Any, cast

import pytest
import redis.asyncio as redis

from atep.core.errors import RateLimitExceededError, RateLimitUnavailableError
from atep.core.rate_limit import RateLimitPolicy, consume_rate_limit


class FakeRedis:
    def __init__(self, results: list[object] | None = None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[tuple[str, int, tuple[str, ...]]] = []

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> Any:
        self.calls.append((script, numkeys, keys_and_args))
        if self.error is not None:
            raise self.error
        return self.results.pop(0)


def redis_stub(fake: FakeRedis) -> redis.Redis:
    return cast(redis.Redis, fake)


@pytest.mark.asyncio
async def test_atomic_counter_returns_safe_headers_without_exposing_identity() -> None:
    fake = FakeRedis(results=[[3, 42_001]])
    result = await consume_rate_limit(
        redis_stub(fake),
        policy=RateLimitPolicy(name="authentication-account", limit=5, window_seconds=60),
        identity="account:hashed-value",
    )

    assert result.limit == 5
    assert result.remaining == 2
    assert result.reset_after == 43
    _, numkeys, arguments = fake.calls[0]
    assert numkeys == 1
    assert arguments[0] == "atep:rate-limit:authentication-account:account:hashed-value"
    assert arguments[1] == "60000"


@pytest.mark.asyncio
async def test_counter_rejects_request_after_limit_with_retry_metadata() -> None:
    fake = FakeRedis(results=[[6, 15_000]])

    with pytest.raises(RateLimitExceededError) as captured:
        await consume_rate_limit(
            redis_stub(fake),
            policy=RateLimitPolicy(name="api", limit=5, window_seconds=60),
            identity="client:hashed-value",
        )

    assert captured.value.details == {"limit": 5, "remaining": 0, "reset_after": 15}
    assert captured.value.headers == {
        "Retry-After": "15",
        "X-RateLimit-Limit": "5",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "15",
    }


@pytest.mark.asyncio
async def test_redis_failure_does_not_silently_bypass_rate_limit() -> None:
    fake = FakeRedis(error=TimeoutError("redis unavailable"))

    with pytest.raises(RateLimitUnavailableError) as captured:
        await consume_rate_limit(
            redis_stub(fake),
            policy=RateLimitPolicy(name="api", limit=5, window_seconds=60),
            identity="client:hashed-value",
        )

    assert captured.value.status_code == 503
    assert captured.value.code == "rate_limit_unavailable"
    assert captured.value.headers == {"Retry-After": "1"}
