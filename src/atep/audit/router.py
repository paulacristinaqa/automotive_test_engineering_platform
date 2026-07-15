from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.schemas import AuditRecordPage, AuditRecordResponse, AuditSearch
from atep.audit.service import (
    audit_records_csv,
    list_audit_records,
    record_audit,
    require_audit_record,
)
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id

router = APIRouter(prefix="/audit-records", tags=["audit"])
audit_read = require_permissions(PermissionName.AUDIT_READ.value)
audit_export = require_permissions(PermissionName.AUDIT_EXPORT.value)


@router.get("", response_model=AuditRecordPage)
async def list_audit_records_endpoint(
    filters: Annotated[AuditSearch, Depends()],
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(audit_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> AuditRecordPage:
    records, total = await list_audit_records(session, filters=filters, limit=limit, offset=offset)
    return AuditRecordPage(
        items=[AuditRecordResponse.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/export")
async def export_audit_records_endpoint(
    filters: Annotated[AuditSearch, Depends()],
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(audit_export)],
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1_000,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> Response:
    records, _ = await list_audit_records(session, filters=filters, limit=limit, offset=offset)
    record_audit(
        session,
        actor_user_id=actor.id,
        action="audit.records.exported",
        resource_type="audit_export",
        resource_id=actor.id,
        correlation_id=request_correlation_id(request),
        details={
            "filters": filters.model_dump(mode="json", exclude_none=True),
            "limit": limit,
            "offset": offset,
            "exported_count": len(records),
        },
    )
    await session.commit()
    return Response(
        content=audit_records_csv(records).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="atep-audit-records.csv"'},
    )


@router.get("/{record_id}", response_model=AuditRecordResponse)
async def get_audit_record_endpoint(
    record_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(audit_read)],
) -> AuditRecordResponse:
    return AuditRecordResponse.model_validate(await require_audit_record(session, record_id))
