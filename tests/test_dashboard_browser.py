import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from starlette.datastructures import Headers, QueryParams

from atep.core.config import Settings
from atep.dashboard import browser


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "http://remote.example",
        "https://host/path",
        "https://user@host",
        "https://host:99999",
    ],
)
def test_browser_origin_configuration_rejects_unsafe_values(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret="x" * 32, dashboard_browser_origins=origin)


def test_browser_origin_configuration_is_disabled_by_default() -> None:
    assert Settings(_env_file=None, jwt_secret="x" * 32).dashboard_browser_origins == ""
    settings = Settings(
        _env_file=None,
        jwt_secret="x" * 32,
        dashboard_browser_origins="https://host,http://localhost:8080,http://[::1]:8080",
    )
    assert "http://localhost:8080" in settings.dashboard_browser_origins


@pytest.mark.parametrize(
    "origins,query,authorization,expected",
    [
        (["http://localhost:8080"], "", False, True),
        ([], "", False, False),
        (["null"], "", False, False),
        (["https://other.example"], "", False, False),
        (["http://localhost:8080", "http://localhost:8080"], "", False, False),
        (["http://localhost:8080"], "token=secret", False, False),
        (["http://localhost:8080"], "", True, False),
    ],
)
def test_browser_transport_requires_exact_origin_and_no_alternative_credentials(
    monkeypatch: pytest.MonkeyPatch,
    origins: list[str],
    query: str,
    authorization: bool,
    expected: bool,
) -> None:
    monkeypatch.setattr(
        browser,
        "get_settings",
        lambda: SimpleNamespace(dashboard_browser_origins="http://localhost:8080"),
    )
    headers = [(b"origin", origin.encode()) for origin in origins]
    if authorization:
        headers.append((b"authorization", b"Bearer secret"))
    ws: Any = SimpleNamespace(headers=Headers(raw=headers), query_params=QueryParams(query))
    assert browser.browser_transport_allowed(ws) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "[]",
        "{}",
        '{"type":"wrong","access_token":"secret"}',
        '{"type":"atep.dashboard.authenticate.v1","access_token":null}',
        '{"type":"atep.dashboard.authenticate.v1","access_token":""}',
        "x" * 4097,
    ],
)
async def test_browser_auth_rejects_malformed_frames_without_echo(raw: str) -> None:
    ws: Any = SimpleNamespace(
        receive=AsyncMock(return_value={"type": "websocket.receive", "text": raw}),
        close=AsyncMock(),
    )
    assert await browser.receive_browser_token(ws) is None
    ws.close.assert_awaited_once_with(code=4401, reason="Dashboard authentication required")


@pytest.mark.asyncio
async def test_browser_auth_accepts_bounded_versioned_frame() -> None:
    ws: Any = SimpleNamespace(
        receive=AsyncMock(
            return_value={
                "type": "websocket.receive",
                "text": json.dumps(
                    {"type": "atep.dashboard.authenticate.v1", "access_token": "token"}
                ),
            }
        ),
        close=AsyncMock(),
    )
    assert await browser.receive_browser_token(ws) == "token"
    ws.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_auth_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser, "AUTH_TIMEOUT_SECONDS", 0.01)
    ws: Any = SimpleNamespace(receive=asyncio.Event().wait, close=AsyncMock())
    assert await browser.receive_browser_token(ws) is None
    assert ws.close.call_args.kwargs["code"] == 4401


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnected", [True, False])
async def test_browser_auth_disconnect_and_binary_frames(disconnected: bool) -> None:
    message = (
        {"type": "websocket.disconnect"}
        if disconnected
        else {"type": "websocket.receive", "bytes": b"secret"}
    )
    ws: Any = SimpleNamespace(receive=AsyncMock(return_value=message), close=AsyncMock())
    assert await browser.receive_browser_token(ws) is None
    if disconnected:
        ws.close.assert_not_awaited()
    else:
        assert ws.close.call_args.kwargs["code"] == 4401
