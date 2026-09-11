"""Bounded periodic snapshots, not event-by-event vehicle telemetry."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from atep.core.config import get_settings
from atep.core.security import InvalidTokenError, decode_access_token
from atep.dashboard.exports import ExportView, generate_export
from atep.db.session import session_factory
from atep.identity.permissions import PermissionName
from atep.identity.service import get_user_by_id

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
REFRESH_SECONDS = 30
MAX_SNAPSHOTS = 10
SEND_TIMEOUT_SECONDS = 5
# Fail fast rather than queueing expensive snapshot work. Limit is per worker process.
connection_slots = asyncio.Semaphore(16)


async def authorized(websocket: WebSocket) -> bool:
    scheme, _, token = websocket.headers.get("authorization", "").partition(" ")
    if scheme.casefold() != "bearer" or not token:
        await websocket.close(code=4401, reason="Authentication required")
        return False
    try:
        user_id = decode_access_token(token, get_settings())
    except InvalidTokenError:
        await websocket.close(code=4401, reason="Invalid access token")
        return False
    async with session_factory() as session:
        user = await get_user_by_id(session, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=4401, reason="Invalid access token")
            return False
        if PermissionName.DASHBOARD_READ.value not in user.permission_names:
            await websocket.close(code=4403, reason="Permission denied")
            return False
    return True


@router.websocket("/stream/{view}")
async def stream_dashboard(websocket: WebSocket, view: ExportView) -> None:
    acquired = False
    try:
        async with asyncio.timeout(10):
            if not await authorized(websocket):
                return
        if connection_slots.locked():
            await websocket.close(code=1013, reason="Dashboard stream capacity reached")
            return
        await connection_slots.acquire()
        acquired = True
        await websocket.accept()
        for sequence in range(1, MAX_SNAPSHOTS + 1):
            async with asyncio.timeout(15):
                if not await authorized(websocket):
                    return
                async with session_factory() as session:
                    payload = await generate_export(session, view=view, window_hours=24)
                # Do not send a snapshot if access changed while the queries were executing.
                if not await authorized(websocket):
                    return
            observed_at = datetime.now(UTC)
            frame = {
                "type": "atep.dashboard.snapshot.v1",
                "sequence": sequence,
                "observed_at": observed_at.isoformat(),
                "refresh_not_before": (
                    observed_at + timedelta(seconds=REFRESH_SECONDS)
                ).isoformat(),
                "refresh_interval_seconds": REFRESH_SECONDS,
                "freshness_basis": "server_query_not_vehicle_measurement",
                "snapshot": json.loads(payload),
            }
            async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
                await websocket.send_json(frame)
            if sequence == MAX_SNAPSHOTS:
                await websocket.close(
                    code=1000, reason="Snapshot limit reached; reconnect if needed"
                )
                return
            try:
                async with asyncio.timeout(REFRESH_SECONDS):
                    message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                await websocket.close(code=1008, reason="Dashboard stream is read-only")
                return
            except TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception:
        # Deliberately omit payloads, credentials and exception text from output/logs.
        try:
            await websocket.close(code=1013, reason="Dashboard stream temporarily unavailable")
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        if acquired:
            connection_slots.release()
