from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.artifacts.schemas import ArtifactCreate, ArtifactResponse
from atep.artifacts.service import create_artifact_metadata
from atep.artifacts.storage import FilesystemArtifactStore, ObjectTooLargeError, StoredObject
from atep.audit.models import AuditRecord
from atep.core.errors import TestArtifactConflictError as ArtifactConflictError
from atep.events.models import OutboxEvent
from atep.test_runs.models import TestRun as RunRecord


class NestedTransaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakeSession:
    def __init__(self, *scalar_values: Any) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


NOW = datetime(2026, 8, 5, 14, 0, tzinfo=UTC)


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


def run_record() -> RunRecord:
    return RunRecord(
        id=uuid4(),
        run_id="artifact-test-run-001",
        vehicle_id=uuid4(),
        requested_by_user_id=uuid4(),
        environment_profile_id=None,
        environment_profile_version=None,
        environment_snapshot=None,
        name="Artifact evidence test",
        suite="smoke",
        metadata_={},
        status="passed",
        progress_percent=100,
        version=2,
        summary="Passed",
        started_at=NOW,
        completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def command(*, filename: str = "battery-report.json") -> ArtifactCreate:
    return ArtifactCreate(
        artifact_id="artifact-report-001",
        kind="report",
        filename=filename,
        media_type="application/json",
    )


def test_contract_rejects_path_like_and_nonportable_filenames() -> None:
    for filename in ("../report.json", "folder/report.json", "folder\\report.json", "."):
        with pytest.raises(ValidationError, match="path separators|portable"):
            command(filename=filename)


@pytest.mark.asyncio
async def test_filesystem_store_hashes_streams_and_removes_oversized_objects(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path / "objects")
    await store.ensure_ready()
    stored = await store.put("test-runs/run/object", chunks(b"battery", b"-report"), max_bytes=64)
    assert stored.size_bytes == 14
    assert stored.sha256 == "f9a0eabde18fc44352db7e683b9d8a20622ead65b204df02fdc8b7381fe595cf"
    assert b"".join([part async for part in store.stream(stored.key)]) == b"battery-report"
    assert await store.exists(stored.key) is True

    with pytest.raises(ObjectTooLargeError):
        await store.put("test-runs/run/oversized", chunks(b"1234", b"5"), max_bytes=4)
    assert await store.exists("test-runs/run/oversized") is False
    assert not list((tmp_path / "objects").rglob("*.upload"))

    with pytest.raises(ValueError, match="escapes"):
        await store.put("../escape", chunks(b"unsafe"), max_bytes=64)


@pytest.mark.asyncio
async def test_metadata_creation_is_idempotent_audited_and_evented() -> None:
    run = run_record()
    actor_id = uuid4()
    stored = StoredObject(key="test-runs/run/object-1", size_bytes=14, sha256="a" * 64)
    session = FakeSession(None)
    artifact, duplicate = await create_artifact_metadata(
        cast(AsyncSession, session),
        test_run=run,
        command=command(),
        stored=stored,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
        now=NOW,
    )
    assert duplicate is False
    assert artifact.object_key == stored.key
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.test_artifact.stored.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "test_artifact.stored"
    ]

    retry = FakeSession(artifact)
    returned, duplicate = await create_artifact_metadata(
        cast(AsyncSession, retry),
        test_run=run,
        command=command(),
        stored=StoredObject(key="temporary-retry", size_bytes=14, sha256="a" * 64),
        actor_user_id=actor_id,
        correlation_id=None,
    )
    assert returned is artifact
    assert duplicate is True
    assert retry.added == []

    with pytest.raises(ArtifactConflictError):
        await create_artifact_metadata(
            cast(AsyncSession, FakeSession(artifact)),
            test_run=run,
            command=command(),
            stored=StoredObject(key="different", size_bytes=15, sha256="b" * 64),
            actor_user_id=actor_id,
            correlation_id=None,
        )


def test_artifact_model_does_not_expose_object_key_in_response_contract() -> None:
    assert "object_key" not in ArtifactResponse.model_fields
