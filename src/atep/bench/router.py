from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from atep.bench.export_service import MAX_TRACE_FRAMES, export_dbc, load_trace_page
from atep.bench.vector_dbc import encode_dbc
from atep.bench.vector_trace import render_asc, render_blf
from atep.can_network.router import can_read
from atep.can_network.service import require_can_network
from atep.db.session import get_session
from atep.identity.models import User
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/can-networks/exports", tags=["virtual-bench"])


class TraceFormat(StrEnum):
    ASC = "asc"
    BLF = "blf"


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get(
    "/dbc",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def export_dbc_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(can_read)],
) -> Response:
    vehicle = await require_vehicle(session, vehicle_id)
    network = await require_can_network(session, vehicle=vehicle)
    text = await export_dbc(session, network=network)
    return Response(
        content=encode_dbc(text),
        media_type="application/octet-stream",
        headers=_attachment(f"{vehicle.identifier}-{network.identifier}.dbc"),
    )


@router.get(
    "/trace",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}, "text/plain": {}}}},
)
async def export_trace_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(can_read)],
    trace_format: Annotated[TraceFormat, Query(alias="format")] = TraceFormat.ASC,
    after_sequence: Annotated[int, Query(ge=0, le=2**62)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_TRACE_FRAMES)] = MAX_TRACE_FRAMES,
) -> Response:
    vehicle = await require_vehicle(session, vehicle_id)
    network = await require_can_network(session, vehicle=vehicle)
    page = await load_trace_page(
        session, network=network, after_sequence=after_sequence, limit=limit
    )
    headers = _attachment(f"{vehicle.identifier}-{network.identifier}.{trace_format.value}")
    headers["X-ATEP-Frame-Count"] = str(len(page.frames))
    headers["X-ATEP-Truncated"] = "true" if page.truncated else "false"
    if page.last_sequence is not None:
        headers["X-ATEP-Last-Sequence"] = str(page.last_sequence)
    if trace_format is TraceFormat.BLF:
        content = render_blf(page.frames, measurement_start=network.created_at)
        return Response(content=content, media_type="application/octet-stream", headers=headers)
    text = render_asc(page.frames, measurement_start=network.created_at)
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)
