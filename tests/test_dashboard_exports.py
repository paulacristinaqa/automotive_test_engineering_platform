import asyncio
import json
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.errors import ApplicationError
from atep.dashboard import exports
from atep.dashboard.evidence import EvidenceReadiness, evidence_gaps


def sample() -> EvidenceReadiness:
    now = datetime.now(UTC)
    return EvidenceReadiness(
        generated_at=now,
        window_start=now,
        window_hours=24,
        diagnostic_flash_states=[],
        requirement_coverage_states=[],
        audit_outcomes=[],
        gaps=evidence_gaps(),
        limitations=[],
    )


@pytest.mark.asyncio
async def test_export_preserves_source_contract_and_gap_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = AsyncMock(return_value=sample())
    monkeypatch.setattr(exports, "build_evidence_readiness", builder)
    session = cast(AsyncSession, object())
    payload = await exports.generate_export(session, view="evidence-readiness", window_hours=24)
    body = json.loads(payload)
    assert body["contract_version"] == "dashboard-export-v1"
    assert body["server_retention"] == "not_persisted"
    assert body["data"]["assessment"] == "not_assessed"
    assert len(body["data"]["gaps"]) == 4
    builder.assert_awaited_once_with(session, window_hours=24)
    monkeypatch.setattr(exports, "MAX_EXPORT_BYTES", len(payload))
    assert await exports.generate_export(session, view="evidence-readiness", window_hours=24)
    monkeypatch.setattr(exports, "MAX_EXPORT_BYTES", len(payload) - 1)
    with pytest.raises(ApplicationError) as error:
        await exports.generate_export(session, view="evidence-readiness", window_hours=24)
    assert error.value.code == "dashboard_export_too_large"
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_export_timeout_cancels_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    cancelled = asyncio.Event()

    async def blocked(*args: object, **kwargs: object) -> EvidenceReadiness:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return sample()

    monkeypatch.setattr(exports, "build_evidence_readiness", blocked)
    monkeypatch.setattr(exports, "EXPORT_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(ApplicationError) as error:
        await exports.generate_export(
            cast(AsyncSession, object()), view="evidence-readiness", window_hours=24
        )
    assert error.value.code == "dashboard_export_timeout"
    assert error.value.status_code == 504
    assert cancelled.is_set()
