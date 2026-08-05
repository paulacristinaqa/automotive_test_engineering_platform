from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from atep.artifacts.storage import (
    FilesystemArtifactStore,
    InstrumentedArtifactStore,
    ObjectNotAvailableError,
)
from atep.core.config import Settings
from atep.core.observability import Observability


def observability() -> Observability:
    return Observability(
        Settings(
            jwt_secret="dependency-metrics-test-secret-at-least-32-characters",
            environment="test",
            tracing_enabled=False,
        )
    )


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


def test_dependency_metrics_accept_only_bounded_labels() -> None:
    metrics = observability()
    metrics.observe_dependency_check(dependency="postgres", outcome="ready", duration_seconds=0.01)
    metrics.observe_dependency_check(
        dependency="redis", outcome="unavailable", duration_seconds=0.02
    )

    text = metrics.render_metrics()[0].decode()
    assert 'atep_dependency_checks_total{dependency="postgres",outcome="ready"} 1.0' in text
    assert 'atep_dependency_ready{dependency="redis"} 0.0' in text
    assert 'atep_dependency_check_duration_seconds_count{dependency="postgres"} 1.0' in text

    with pytest.raises(ValueError, match="unsupported dependency"):
        metrics.observe_dependency_check(
            dependency="postgres-primary-secret", outcome="ready", duration_seconds=0.01
        )
    assert "postgres-primary-secret" not in metrics.render_metrics()[0].decode()


@pytest.mark.asyncio
async def test_instrumented_store_reports_operations_bytes_capacity_and_failures(
    tmp_path: Path,
) -> None:
    metrics = observability()
    filesystem_store = FilesystemArtifactStore(tmp_path / "objects")
    store = InstrumentedArtifactStore(
        filesystem_store, metrics, capacity_provider=filesystem_store.capacity
    )
    await store.ensure_ready()
    stored = await store.put(
        "test-runs/private-run/object-secret", chunks(b"battery", b"-report"), max_bytes=64
    )
    assert await store.exists(stored.key) is True
    assert b"".join([chunk async for chunk in store.stream(stored.key)]) == b"battery-report"
    with pytest.raises(ValueError, match="escapes"):
        await store.put("../private-object", chunks(b"unsafe"), max_bytes=64)
    with pytest.raises(ObjectNotAvailableError):
        b"".join([chunk async for chunk in store.stream("missing-object")])
    await store.delete(stored.key)

    text = metrics.render_metrics()[0].decode()
    assert 'atep_artifact_store_operations_total{operation="put",outcome="success"} 1.0' in text
    assert 'atep_artifact_store_operations_total{operation="put",outcome="rejected"} 1.0' in text
    assert 'atep_artifact_store_operations_total{operation="stream",outcome="success"} 1.0' in text
    assert 'atep_artifact_store_operations_total{operation="stream",outcome="error"} 1.0' in text
    assert 'atep_artifact_store_bytes_total{direction="write"} 14.0' in text
    assert 'atep_artifact_store_bytes_total{direction="read"} 14.0' in text
    assert "atep_artifact_store_capacity_bytes" in text
    assert "atep_artifact_store_free_bytes" in text
    assert "private-run" not in text
    assert "object-secret" not in text

    with pytest.raises(ValueError, match="unsupported artifact-store operation"):
        metrics.observe_artifact_store_operation(
            operation="private-object-secret",
            outcome="success",
            duration_seconds=0.01,
        )
    assert "private-object-secret" not in metrics.render_metrics()[0].decode()
