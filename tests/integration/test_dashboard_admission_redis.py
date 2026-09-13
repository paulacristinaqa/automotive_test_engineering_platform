"""Exercise the production admission helper with two independent real Redis clients."""

import asyncio
import hashlib
import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import redis.asyncio as redis

from atep.dashboard.admission import HANDSHAKE_POLICY, admit_dashboard_handshake

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_dashboard_handshake_budget_is_shared_and_expires() -> None:
    url = os.getenv("ATEP_INTEGRATION_REDIS_URL")
    assert url, "ATEP_INTEGRATION_REDIS_URL is required"
    peer = "integration-" + uuid4().hex
    identity = "peer:" + hashlib.sha256(peer.encode()).hexdigest()
    key = f"atep:rate-limit:{HANDSHAKE_POLICY.name}:{identity}"
    clients = [
        redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2) for _ in range(2)
    ]

    def socket(index: int) -> Any:
        return SimpleNamespace(
            client=SimpleNamespace(host=peer),
            app=SimpleNamespace(state=SimpleNamespace(redis=clients[index])),
            headers={"authorization": f"Bearer rotated-{index}"},
            close=AsyncMock(),
        )

    try:
        async with asyncio.timeout(10):
            # Alternating clients model separate worker pools without parallel load.
            for attempt in range(HANDSHAKE_POLICY.limit):
                assert await admit_dashboard_handshake(socket(attempt % 2))
            denied = socket(1)
            assert not await admit_dashboard_handshake(denied)
            assert denied.close.call_args.kwargs["code"] == 1013
            assert await clients[0].get(key) == b"31"
            assert 0 < await clients[0].pttl(key) <= HANDSHAKE_POLICY.window_seconds * 1000
            # Accelerate only this unique test key, not the production policy or other peers.
            await clients[0].pexpire(key, 1)
            for _ in range(50):
                if not await clients[1].exists(key):
                    break
                await asyncio.sleep(0.01)
            assert not await clients[1].exists(key)
            assert await admit_dashboard_handshake(socket(1))
            assert await clients[0].get(key) == b"1"
    finally:
        try:
            await clients[0].delete(key)
        finally:
            for client in clients:
                await client.aclose()
