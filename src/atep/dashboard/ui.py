"""Opt-in same-origin dashboard shell; API authorization remains authoritative."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from atep.core.config import Settings, get_settings

router = APIRouter(include_in_schema=False)
PACKAGED_ASSETS = Path(__file__).with_name("web")
ASSETS = (
    PACKAGED_ASSETS if PACKAGED_ASSETS.is_dir() else Path(__file__).parents[3] / "clients/dashboard"
)
FILES = {
    "index.html": "text/html",
    "dashboard.css": "text/css",
    "dashboard.mjs": "text/javascript",
    "session-client.mjs": "text/javascript",
    "stream-client.mjs": "text/javascript",
}
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def asset(name: str, settings: Settings) -> FileResponse:
    if not settings.dashboard_ui_enabled or name not in FILES:
        raise HTTPException(404, "Not found")
    return FileResponse(ASSETS / name, media_type=FILES[name], headers=HEADERS)


@router.get("/dashboard/")
async def dashboard_index(settings: Annotated[Settings, Depends(get_settings)]) -> FileResponse:
    return asset("index.html", settings)


@router.get("/dashboard/{name}")
async def dashboard_asset(
    name: str, settings: Annotated[Settings, Depends(get_settings)]
) -> FileResponse:
    return asset(name, settings)
