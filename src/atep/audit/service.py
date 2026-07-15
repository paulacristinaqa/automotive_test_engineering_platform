import csv
import json
from io import StringIO
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.audit.schemas import AuditSearch
from atep.core.errors import ResourceNotFoundError


def record_audit(
    session: AsyncSession,
    *,
    actor_user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: UUID,
    correlation_id: UUID | None,
    details: dict[str, Any] | None = None,
) -> AuditRecord:
    record = AuditRecord(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        details=details or {},
    )
    session.add(record)
    return record


def _filtered_query(filters: AuditSearch) -> Select[tuple[AuditRecord]]:
    query = select(AuditRecord)
    if filters.actor_user_id is not None:
        query = query.where(AuditRecord.actor_user_id == filters.actor_user_id)
    if filters.action is not None:
        query = query.where(AuditRecord.action == filters.action)
    if filters.resource_type is not None:
        query = query.where(AuditRecord.resource_type == filters.resource_type)
    if filters.resource_id is not None:
        query = query.where(AuditRecord.resource_id == filters.resource_id)
    if filters.outcome is not None:
        query = query.where(AuditRecord.outcome == filters.outcome)
    if filters.correlation_id is not None:
        query = query.where(AuditRecord.correlation_id == filters.correlation_id)
    if filters.created_from is not None:
        query = query.where(AuditRecord.created_at >= filters.created_from)
    if filters.created_to is not None:
        query = query.where(AuditRecord.created_at <= filters.created_to)
    return query


async def list_audit_records(
    session: AsyncSession,
    *,
    filters: AuditSearch,
    limit: int,
    offset: int,
) -> tuple[list[AuditRecord], int]:
    filtered = _filtered_query(filters)
    total = await session.scalar(select(func.count()).select_from(filtered.subquery()))
    result = await session.execute(
        filtered.order_by(AuditRecord.created_at.desc(), AuditRecord.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_audit_record(session: AsyncSession, record_id: UUID) -> AuditRecord:
    record = await session.get(AuditRecord, record_id)
    if record is None:
        raise ResourceNotFoundError("audit_record")
    return record


def audit_records_csv(records: list[AuditRecord]) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        (
            "id",
            "created_at",
            "actor_user_id",
            "action",
            "resource_type",
            "resource_id",
            "outcome",
            "correlation_id",
            "details_json",
        )
    )
    for record in records:
        writer.writerow(
            tuple(
                _safe_csv_cell(value)
                for value in (
                    str(record.id),
                    record.created_at.isoformat(),
                    str(record.actor_user_id) if record.actor_user_id else "system",
                    record.action,
                    record.resource_type,
                    str(record.resource_id),
                    record.outcome,
                    str(record.correlation_id) if record.correlation_id else "",
                    json.dumps(record.details, sort_keys=True, separators=(",", ":")),
                )
            )
        )
    return "\ufeff" + output.getvalue()


def _safe_csv_cell(value: str) -> str:
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value
