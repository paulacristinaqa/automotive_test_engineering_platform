import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from atep.core.security import InvalidTokenError
from atep.dashboard import realtime


def socket() -> Any:
    return SimpleNamespace(
        headers={"authorization": "Bearer test"},
        close=AsyncMock(),
        accept=AsyncMock(),
        send_json=AsyncMock(),
        receive=AsyncMock(return_value={"type": "websocket.disconnect"}),
    )


def setup(monkeypatch: pytest.MonkeyPatch) -> None:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=object())
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(realtime, "session_factory", lambda: context)
    monkeypatch.setattr(realtime, "connection_slots", asyncio.Semaphore(1))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "active,permitted,expected", [(True, True, None), (False, True, 4401), (True, False, 4403)]
)
async def test_stream_checks_live_user_permissions(
    monkeypatch: pytest.MonkeyPatch, active: bool, permitted: bool, expected: int | None
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(realtime, "decode_access_token", lambda *args: "user-id")
    monkeypatch.setattr(
        realtime,
        "get_user_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                is_active=active, permission_names={"dashboard:read"} if permitted else set()
            )
        ),
    )
    ws = socket()
    assert await realtime.authorized(cast(WebSocket, ws)) is (expected is None)
    if expected:
        assert ws.close.call_args.kwargs["code"] == expected


@pytest.mark.asyncio
async def test_stream_requires_header_not_query_token() -> None:
    ws = socket()
    ws.headers = {}
    assert not await realtime.authorized(cast(WebSocket, ws))
    assert ws.close.call_args.kwargs["code"] == 4401


@pytest.mark.asyncio
async def test_expired_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(realtime, "decode_access_token", MagicMock(side_effect=InvalidTokenError()))
    ws = socket()
    assert not await realtime.authorized(cast(WebSocket, ws))
    assert ws.close.call_args.kwargs["code"] == 4401


@pytest.mark.asyncio
@pytest.mark.parametrize("slow", [False, True])
async def test_client_messages_and_slow_consumers_close_and_release(
    monkeypatch: pytest.MonkeyPatch, slow: bool
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(realtime, "authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(realtime, "generate_export", AsyncMock(return_value=b"{}"))
    ws = socket()
    if slow:
        monkeypatch.setattr(realtime, "SEND_TIMEOUT_SECONDS", 0.01)

        async def blocked(frame: object) -> None:
            await asyncio.Event().wait()

        ws.send_json = blocked
    else:
        ws.receive = AsyncMock(return_value={"type": "websocket.receive", "text": "refresh"})
    await realtime.stream_dashboard(cast(WebSocket, ws), "operations")
    assert ws.close.call_args.kwargs["code"] == (1013 if slow else 1008)
    assert not realtime.connection_slots.locked()


@pytest.mark.asyncio
async def test_snapshot_freshness_disconnect_and_slot_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    auth = AsyncMock(return_value=True)
    monkeypatch.setattr(realtime, "authorized", auth)
    monkeypatch.setattr(
        realtime, "generate_export", AsyncMock(return_value=b'{"view":"operations"}')
    )
    ws = socket()
    await realtime.stream_dashboard(cast(WebSocket, ws), "operations")
    frame = ws.send_json.call_args.args[0]
    assert frame["sequence"] == 1
    assert frame["refresh_interval_seconds"] == 30
    assert frame["freshness_basis"] == "server_query_not_vehicle_measurement"
    assert auth.await_count == 3
    assert not realtime.connection_slots.locked()


@pytest.mark.asyncio
async def test_revocation_during_generation_prevents_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(realtime, "authorized", AsyncMock(side_effect=[True, True, False]))
    monkeypatch.setattr(realtime, "generate_export", AsyncMock(return_value=b"{}"))
    ws = socket()
    await realtime.stream_dashboard(cast(WebSocket, ws), "operations")
    ws.send_json.assert_not_awaited()
    assert not realtime.connection_slots.locked()


@pytest.mark.asyncio
async def test_capacity_rejects_without_building(monkeypatch: pytest.MonkeyPatch) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(realtime, "authorized", AsyncMock(return_value=True))
    await realtime.connection_slots.acquire()
    ws = socket()
    await realtime.stream_dashboard(cast(WebSocket, ws), "operations")
    assert ws.close.call_args.kwargs["code"] == 1013
    ws.accept.assert_not_awaited()
    assert realtime.connection_slots.locked()


@pytest.mark.asyncio
async def test_periodic_refresh_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(realtime, "authorized", AsyncMock(return_value=True))
    monkeypatch.setattr(realtime, "generate_export", AsyncMock(return_value=b"{}"))
    monkeypatch.setattr(realtime, "REFRESH_SECONDS", 0.01)
    monkeypatch.setattr(realtime, "MAX_SNAPSHOTS", 2)
    ws = socket()
    ws.receive = asyncio.Event().wait
    await realtime.stream_dashboard(cast(WebSocket, ws), "operations")
    assert ws.send_json.await_count == 2
    assert ws.close.call_args.kwargs["code"] == 1000
    assert not realtime.connection_slots.locked()
