from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from prometheus_client import generate_latest
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings
from atep.core.observability import Observability
from atep.events.observability import OutboxObservability
from atep.events.worker import measure_outbox_backlog
from atep.test_jobs.scheduler import measure_due_test_jobs
from atep.test_runs.realtime import publish_test_run_update
from atep.test_runs.schemas import TestRunStreamEvent as StreamEventSchema


class AggregateResult:
    def __init__(self, values: tuple[int, datetime | None]) -> None:
        self.values = values

    def one(self) -> tuple[int, datetime | None]:
        return self.values


class AggregateSession:
    def __init__(self, values: tuple[int, datetime | None]) -> None:
        self.values = values

    async def execute(self, _: Any) -> AggregateResult:
        return AggregateResult(self.values)


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def publish(self, _: str, __: str) -> None:
        if self.fail:
            raise ConnectionError("controlled Redis failure")


class FakeStreamEvent:
    class TestRun:
        run_id = "run-domain-observability"

    test_run = TestRun()

    def model_dump_json(self) -> str:
        return "{}"


def api_observability() -> Observability:
    return Observability(
        Settings(
            jwt_secret="domain-observability-test-secret-at-least-32-characters",
            environment="test",
        )
    )


@pytest.mark.asyncio
async def test_backlog_measurements_are_aggregated_and_never_return_identifiers() -> None:
    observed_at = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    oldest = observed_at - timedelta(seconds=75)

    outbox = await measure_outbox_backlog(
        cast(AsyncSession, AggregateSession((4, oldest))), now=observed_at
    )
    jobs = await measure_due_test_jobs(
        cast(AsyncSession, AggregateSession((2, oldest))), now=observed_at
    )

    assert outbox.count == 4
    assert outbox.oldest_age_seconds == 75
    assert jobs.count == 2
    assert jobs.oldest_age_seconds == 75
    assert set(outbox.__dict__) == {"count", "oldest_age_seconds"}
    assert set(jobs.__dict__) == {"count", "oldest_age_seconds"}


def test_outbox_worker_metrics_use_only_bounded_outcome_labels() -> None:
    observability = OutboxObservability()
    observability.update_backlog(count=3, oldest_age_seconds=45.5)
    observability.publication_attempts.labels("success").inc(2)
    observability.publication_attempts.labels("error").inc()
    text = generate_latest(observability.registry).decode()

    assert "atep_outbox_worker_up 0.0" in text
    assert "atep_outbox_unpublished_events 3.0" in text
    assert "atep_outbox_oldest_unpublished_age_seconds 45.5" in text
    assert 'atep_outbox_publication_attempts_total{outcome="success"} 2.0' in text
    assert 'atep_outbox_publication_attempts_total{outcome="error"} 1.0' in text
    assert "run-domain-observability" not in text


@pytest.mark.asyncio
async def test_scheduler_and_live_update_metrics_cover_success_and_failure() -> None:
    observability = api_observability()
    observability.update_test_job_backlog(count=2, oldest_age_seconds=61)
    observability.test_jobs_dispatched.inc()
    observability.websocket_connection_attempts.labels("accepted").inc()
    observability.websocket_messages.labels("snapshot").inc()

    event = cast(StreamEventSchema, FakeStreamEvent())
    await publish_test_run_update(FakeRedis(), event, observability=observability)
    await publish_test_run_update(FakeRedis(fail=True), event, observability=observability)
    text = observability.render_metrics()[0].decode()

    assert "atep_test_jobs_due 2.0" in text
    assert "atep_test_job_oldest_due_age_seconds 61.0" in text
    assert "atep_test_jobs_dispatched_total 1.0" in text
    assert 'atep_test_run_websocket_connection_attempts_total{outcome="accepted"} 1.0' in text
    assert 'atep_test_run_websocket_messages_total{kind="snapshot"} 1.0' in text
    assert 'atep_test_run_live_publish_attempts_total{outcome="success"} 1.0' in text
    assert 'atep_test_run_live_publish_attempts_total{outcome="error"} 1.0' in text
    assert "run-domain-observability" not in text
