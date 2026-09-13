"""Distributed handshake budget; peer identity comes from the trusted ASGI transport."""

import hashlib
from typing import cast

import redis.asyncio as redis
from fastapi import WebSocket

from atep.core.errors import RateLimitExceededError, RateLimitUnavailableError
from atep.core.rate_limit import RateLimitPolicy, consume_rate_limit

HANDSHAKE_POLICY = RateLimitPolicy(name="dashboard-handshake", limit=30, window_seconds=60)


async def admit_dashboard_handshake(websocket: WebSocket) -> bool:
    # Never key by raw credentials or accept untrusted forwarding headers here.
    peer = websocket.client.host if websocket.client is not None else "unknown"
    identity = "peer:" + hashlib.sha256(peer.encode("utf-8")).hexdigest()
    try:
        await consume_rate_limit(
            cast(redis.Redis, websocket.app.state.redis),
            policy=HANDSHAKE_POLICY,
            identity=identity,
        )
    except (RateLimitExceededError, RateLimitUnavailableError):
        await websocket.close(code=1013, reason="Dashboard admission temporarily unavailable")
        return False
    return True
