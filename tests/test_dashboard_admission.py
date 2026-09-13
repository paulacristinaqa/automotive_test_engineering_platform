import hashlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from atep.core.errors import RateLimitExceededError, RateLimitUnavailableError
from atep.dashboard import admission


@pytest.mark.asyncio
@pytest.mark.parametrize("peer", ["127.0.0.1", None])
async def test_handshake_uses_transport_peer_not_credentials(
    monkeypatch: pytest.MonkeyPatch, peer: str | None
) -> None:
    consume = AsyncMock()
    monkeypatch.setattr(admission, "consume_rate_limit", consume)
    ws: Any = SimpleNamespace(
        client=SimpleNamespace(host=peer) if peer else None,
        headers={"authorization": "Bearer secret", "x-forwarded-for": "untrusted"},
        app=SimpleNamespace(state=SimpleNamespace(redis=object())),
        close=AsyncMock(),
    )
    assert await admission.admit_dashboard_handshake(ws)
    assert consume.call_args.kwargs["identity"] == (
        "peer:" + hashlib.sha256((peer or "unknown").encode()).hexdigest()
    )
    assert consume.call_args.kwargs["policy"].limit == 30
    assert consume.call_args.kwargs["policy"].window_seconds == 60
    ws.close.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        RateLimitExceededError(limit=30, remaining=0, reset_after=60),
        RateLimitUnavailableError(),
    ],
)
async def test_handshake_fails_closed(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(admission, "consume_rate_limit", AsyncMock(side_effect=error))
    ws: Any = SimpleNamespace(
        client=None,
        app=SimpleNamespace(state=SimpleNamespace(redis=object())),
        close=AsyncMock(),
    )
    assert not await admission.admit_dashboard_handshake(ws)
    assert ws.close.call_args.kwargs["code"] == 1013
