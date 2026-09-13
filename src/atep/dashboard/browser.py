"""Opt-in browser transport with bounded first-message authentication."""

import asyncio
import json

from fastapi import WebSocket

from atep.core.config import get_settings

AUTH_TIMEOUT_SECONDS = 5
MAX_AUTH_BYTES = 4096


def browser_transport_allowed(websocket: WebSocket) -> bool:
    origins = websocket.headers.getlist("origin")
    allowed = get_settings().dashboard_browser_origins.split(",")
    return (
        len(origins) == 1
        and bool(origins[0])
        and origins[0] in allowed
        and not websocket.query_params
        and "authorization" not in websocket.headers
    )


async def receive_browser_token(websocket: WebSocket) -> str | None:
    try:
        async with asyncio.timeout(AUTH_TIMEOUT_SECONDS):
            message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return None
        raw = message.get("text")
        if (
            not isinstance(raw, str)
            or len(raw) > MAX_AUTH_BYTES
            or len(raw.encode("utf-8")) > MAX_AUTH_BYTES
        ):
            raise ValueError("Invalid authentication frame")
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"type", "access_token"}
            or payload["type"] != "atep.dashboard.authenticate.v1"
            or not isinstance(payload["access_token"], str)
            or not payload["access_token"]
        ):
            raise ValueError("Invalid authentication frame")
        token: str = payload["access_token"]
        return token
    except (TimeoutError, ValueError, RecursionError):
        # Never echo the payload or include parser exception details.
        await websocket.close(code=4401, reason="Dashboard authentication required")
        return None
