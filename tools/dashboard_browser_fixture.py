"""Loopback-only, disposable browser acceptance fixture; never a production login service."""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ORIGIN = "http://localhost:8080"
CLIENT_MODULE = Path(__file__).resolve().parent.parent / "clients/dashboard/stream-client.mjs"
CASE_NAMES = (
    "browser_snapshot",
    "invalid_token",
    "authentication_timeout",
    "read_only",
    "native_origin_denial",
    "client_stale_disconnect",
    "client_reconnect",
    "client_auth_stop",
)


class BrowserResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_agent: str = Field(min_length=1, max_length=300)
    browser_snapshot: Literal["pass", "fail"]
    invalid_token: Literal["pass", "fail"]
    authentication_timeout: Literal["pass", "fail"]
    read_only: Literal["pass", "fail"]
    native_origin_denial: Literal["pass", "fail"]
    client_stale_disconnect: Literal["pass", "fail"]
    client_reconnect: Literal["pass", "fail"]
    client_auth_stop: Literal["pass", "fail"]


def require_local_origin(request: Request) -> None:
    if request.headers.get("origin") != ORIGIN or request.headers.get("host") != "localhost:8080":
        raise HTTPException(403, "Fixture origin denied")


def create_fixture(done: asyncio.Event) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.result = None

    @app.get("/stream-client.mjs")
    async def stream_client() -> FileResponse:
        return FileResponse(
            CLIENT_MODULE,
            media_type="text/javascript",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            Path(__file__).with_name("dashboard_browser_fixture.html"),
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/fixture-token")
    async def token(request: Request) -> JSONResponse:
        require_local_origin(request)
        # Credentials exist only in the disposable runner's environment, not the page or logs.
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                os.environ["ATEP_INTEGRATION_API_URL"] + "/api/v1/auth/token",
                data={
                    "username": os.environ["ATEP_INTEGRATION_ADMIN_EMAIL"],
                    "password": os.environ["ATEP_INTEGRATION_ADMIN_PASSWORD"],
                },
            )
        if response.status_code != 200:
            raise HTTPException(503, "Disposable fixture login unavailable")
        return JSONResponse(
            {"access_token": response.json()["access_token"]}, headers={"Cache-Control": "no-store"}
        )

    @app.post("/result")
    async def result(request: Request, payload: BrowserResult) -> dict[str, str]:
        require_local_origin(request)
        app.state.result = payload
        done.set()
        return {"status": "recorded"}

    return app


async def run() -> int:
    if os.environ.get("ATEP_INTEGRATION_API_URL") != "http://localhost:18000":
        raise RuntimeError("This fixture requires the local disposable integration runner")
    output = Path("dr-evidence/dashboard-browser-acceptance.json")
    # A timed-out run must never leave an older passed report looking current.
    await asyncio.to_thread(output.unlink, missing_ok=True)
    done = asyncio.Event()
    app = create_fixture(done)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8080, log_level="warning", access_log=False)
    )
    task = asyncio.create_task(server.serve())
    print("Browser acceptance fixture: http://localhost:8080 (180-second deadline)", flush=True)
    try:
        await asyncio.wait_for(done.wait(), timeout=180)
    except TimeoutError:
        return 1
    finally:
        server.should_exit = True
        await task
    payload = app.state.result
    if not isinstance(payload, BrowserResult):
        return 1
    passed = all(getattr(payload, name) == "pass" for name in CASE_NAMES)
    report = {
        "schema_version": "dashboard-browser-acceptance-v2",
        "observed_at": datetime.now(UTC).isoformat(),
        "status": "passed" if passed else "failed",
        "fixture": "disposable_admin_token_not_end_user_login",
        **payload.model_dump(),
    }
    await asyncio.to_thread(output.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(output.write_text, json.dumps(report, indent=2), encoding="utf-8")
    print(f"Browser acceptance: {report['status']}; sanitized report: {output}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
