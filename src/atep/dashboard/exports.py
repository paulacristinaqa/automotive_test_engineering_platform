"""Transient exports of aggregate dashboard views; no server-side artifact retention."""

import asyncio
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.errors import ApplicationError
from atep.dashboard.evidence import EvidenceReadiness, build_evidence_readiness
from atep.dashboard.mobility import MobilityAnalytics, build_mobility_analytics
from atep.dashboard.schemas import OperationalOverview
from atep.dashboard.service import build_operations

ExportView = Literal["operations", "mobility", "evidence-readiness"]
MAX_EXPORT_BYTES = 262_144
EXPORT_TIMEOUT_SECONDS = 10.0


class DashboardExport(BaseModel):
    contract_version: Literal["dashboard-export-v1"] = "dashboard-export-v1"
    view: ExportView
    server_retention: Literal["not_persisted"] = "not_persisted"
    data: OperationalOverview | MobilityAnalytics | EvidenceReadiness


async def generate_export(session: AsyncSession, *, view: ExportView, window_hours: int) -> bytes:
    try:
        async with asyncio.timeout(EXPORT_TIMEOUT_SECONDS):
            data: OperationalOverview | MobilityAnalytics | EvidenceReadiness
            if view == "operations":
                data = await build_operations(session, window_hours=window_hours)
            elif view == "mobility":
                data = await build_mobility_analytics(session, window_hours=window_hours)
            else:
                data = await build_evidence_readiness(session, window_hours=window_hours)
            payload = DashboardExport(view=view, data=data).model_dump_json().encode("utf-8")
    except TimeoutError as error:
        raise ApplicationError(
            code="dashboard_export_timeout",
            message="Dashboard export generation timed out.",
            status_code=504,
            headers={"Cache-Control": "no-store"},
        ) from error
    if len(payload) > MAX_EXPORT_BYTES:
        raise ApplicationError(
            code="dashboard_export_too_large",
            message="Dashboard export exceeds the size limit.",
            status_code=422,
            headers={"Cache-Control": "no-store"},
        )
    return payload
