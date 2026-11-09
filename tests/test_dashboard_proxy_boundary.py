import hashlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocket
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from atep.dashboard import admission


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "peer,trusted", [("172.30.241.10", True), ("172.30.241.11", False), ("127.0.0.1", False)]
)
@pytest.mark.parametrize("forwarded", ["198.51.100.7", "203.0.113.8"])
async def test_only_exact_proxy_can_change_admission_identity(
    monkeypatch: pytest.MonkeyPatch, peer: str, trusted: bool, forwarded: str
) -> None:
    consume = AsyncMock()
    monkeypatch.setattr(admission, "consume_rate_limit", consume)
    observed: list[str] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        observed.append(scope["scheme"])
        assert await admission.admit_dashboard_handshake(WebSocket(scope, receive, send))

    scope: Any = {
        "type": "websocket",
        "scheme": "ws",
        "path": "/",
        "query_string": b"",
        "client": (peer, 1234),
        "server": ("api", 8000),
        "headers": [(b"x-forwarded-for", forwarded.encode()), (b"x-forwarded-proto", b"https")],
        "app": SimpleNamespace(state=SimpleNamespace(redis=object())),
    }
    await ProxyHeadersMiddleware(app, trusted_hosts="172.30.241.10")(
        scope, AsyncMock(), AsyncMock()
    )
    expected = forwarded if trusted else peer
    assert (
        consume.call_args.kwargs["identity"]
        == "peer:" + hashlib.sha256(expected.encode()).hexdigest()
    )
    assert observed == ["wss" if trusted else "ws"]
