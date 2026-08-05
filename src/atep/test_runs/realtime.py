import asyncio
from datetime import UTC, datetime

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from atep.core.config import get_settings
from atep.core.observability import Observability
from atep.core.security import InvalidTokenError, decode_access_token
from atep.db.session import session_factory
from atep.identity.permissions import PermissionName
from atep.identity.service import get_user_by_id
from atep.test_runs.schemas import TestRunStreamEvent, test_run_response
from atep.test_runs.service import require_test_run

log = structlog.get_logger()


def test_run_channel(run_id: str) -> str:
    return f"atep:test-runs:{run_id}"


async def publish_test_run_update(
    redis_client: object,
    event: TestRunStreamEvent,
    *,
    observability: Observability | None = None,
) -> None:
    try:
        await redis_client.publish(  # type: ignore[attr-defined]
            test_run_channel(event.test_run.run_id), event.model_dump_json()
        )
        if observability is not None:
            observability.live_publish_attempts.labels("success").inc()
    except Exception as exc:
        if observability is not None:
            observability.live_publish_attempts.labels("error").inc()
        log.warning(
            "test_run_live_update_unavailable",
            run_id=event.test_run.run_id,
            error_type=type(exc).__name__,
        )


async def stream_test_run(websocket: WebSocket, run_id: str) -> None:
    observability: Observability = websocket.app.state.observability
    user = await _authenticate(websocket)
    if user is None:
        observability.websocket_connection_attempts.labels("rejected").inc()
        return

    redis_client = websocket.app.state.redis
    pubsub = redis_client.pubsub()
    channel = test_run_channel(run_id)
    accepted = False
    try:
        await pubsub.subscribe(channel)
        async with session_factory() as session:
            try:
                test_run, vehicle = await require_test_run(session, run_id)
            except Exception as exc:
                if getattr(exc, "code", None) == "test_run_not_found":
                    observability.websocket_connection_attempts.labels("rejected").inc()
                    await websocket.close(code=4404, reason="Test run not found")
                    return
                raise

        await websocket.accept()
        accepted = True
        observability.websocket_connection_attempts.labels("accepted").inc()
        observability.websocket_connections.inc()
        snapshot = TestRunStreamEvent(
            type="atep.test_run.snapshot.v1",
            test_run=test_run_response(test_run, vehicle.identifier),
            occurred_at=datetime.now(UTC),
        )
        await websocket.send_text(snapshot.model_dump_json())
        observability.websocket_messages.labels("snapshot").inc()

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if message is not None:
                data = message["data"]
                await websocket.send_text(
                    data.decode("utf-8") if isinstance(data, bytes) else str(data)
                )
                observability.websocket_messages.labels("update").inc()
            else:
                await websocket.send_json(
                    {
                        "type": "atep.test_run.heartbeat.v1",
                        "run_id": run_id,
                        "occurred_at": datetime.now(UTC).isoformat(),
                    }
                )
                observability.websocket_messages.labels("heartbeat").inc()
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if not accepted:
            observability.websocket_connection_attempts.labels("error").inc()
        log.warning("test_run_stream_closed", run_id=run_id, error_type=type(exc).__name__)
        try:
            await websocket.close(code=1013, reason="Live updates temporarily unavailable")
        except RuntimeError:
            pass
    finally:
        if accepted:
            observability.websocket_connections.dec()
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


async def _authenticate(websocket: WebSocket):  # type: ignore[no-untyped-def]
    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        await websocket.close(code=4401, reason="Authentication required")
        return None
    try:
        user_id = decode_access_token(token, get_settings())
    except InvalidTokenError:
        await websocket.close(code=4401, reason="Invalid access token")
        return None
    async with session_factory() as session:
        user = await get_user_by_id(session, user_id)
        if user is None or not user.is_active:
            await websocket.close(code=4401, reason="Invalid access token")
            return None
        if PermissionName.TEST_RUNS_READ.value not in user.permission_names:
            await websocket.close(code=4403, reason="Permission denied")
            return None
        return user
