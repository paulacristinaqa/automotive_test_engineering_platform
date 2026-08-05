from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.artifacts.models import TestArtifact
from atep.artifacts.schemas import ArtifactCreate, ArtifactKind
from atep.artifacts.storage import StoredObject
from atep.audit.service import record_audit
from atep.core.errors import ResourceNotFoundError, TestArtifactConflictError
from atep.events.outbox import enqueue_event
from atep.test_runs.models import TestRun


async def create_artifact_metadata(
    session: AsyncSession,
    *,
    test_run: TestRun,
    command: ArtifactCreate,
    stored: StoredObject,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[TestArtifact, bool]:
    existing = await session.scalar(
        select(TestArtifact).where(
            TestArtifact.test_run_id == test_run.id,
            TestArtifact.artifact_id == command.artifact_id,
        )
    )
    if existing is not None:
        if not _same_artifact(existing, command, stored):
            raise TestArtifactConflictError()
        return existing, True

    created_at = now or datetime.now(UTC)
    artifact = TestArtifact(
        test_run_id=test_run.id,
        artifact_id=command.artifact_id,
        uploaded_by_user_id=actor_user_id,
        kind=command.kind.value,
        filename=command.filename,
        media_type=command.media_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        object_key=stored.key,
        created_at=created_at,
        updated_at=created_at,
    )
    try:
        async with session.begin_nested():
            session.add(artifact)
            await session.flush()
    except IntegrityError as exc:
        raise TestArtifactConflictError() from exc

    payload = artifact_event_payload(artifact, test_run.run_id)
    enqueue_event(
        session,
        event_type="atep.test_artifact.stored.v1",
        aggregate_type="test_artifact",
        aggregate_id=artifact.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="test_artifact.stored",
        resource_type="test_artifact",
        resource_id=artifact.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return artifact, False


async def require_artifact(
    session: AsyncSession, *, run_id: str, artifact_id: str
) -> tuple[TestArtifact, TestRun]:
    row = (
        await session.execute(
            select(TestArtifact, TestRun)
            .join(TestRun, TestRun.id == TestArtifact.test_run_id)
            .where(TestRun.run_id == run_id, TestArtifact.artifact_id == artifact_id)
        )
    ).one_or_none()
    if row is None:
        raise ResourceNotFoundError("test_artifact")
    return row.tuple()


async def list_artifacts(
    session: AsyncSession,
    *,
    test_run: TestRun,
    limit: int,
    offset: int,
    kind: ArtifactKind | None = None,
) -> tuple[list[TestArtifact], int]:
    query = select(TestArtifact).where(TestArtifact.test_run_id == test_run.id)
    if kind is not None:
        query = query.where(TestArtifact.kind == kind.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(TestArtifact.created_at, TestArtifact.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


def artifact_event_payload(artifact: TestArtifact, run_id: str) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "run_id": run_id,
        "uploaded_by_user_id": str(artifact.uploaded_by_user_id),
        "kind": artifact.kind,
        "filename": artifact.filename,
        "media_type": artifact.media_type,
        "size_bytes": artifact.size_bytes,
        "sha256": artifact.sha256,
        "created_at": artifact.created_at.isoformat(),
    }


def _same_artifact(artifact: TestArtifact, command: ArtifactCreate, stored: StoredObject) -> bool:
    return (
        artifact.kind == command.kind.value
        and artifact.filename == command.filename
        and artifact.media_type == command.media_type
        and artifact.size_bytes == stored.size_bytes
        and artifact.sha256 == stored.sha256
    )
