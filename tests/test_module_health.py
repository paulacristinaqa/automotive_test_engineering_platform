from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atep.registry.schemas import ModuleHealthStatus
from atep.registry.service import summarize_module_health


class AggregateResult:
    def __init__(self, values: tuple[int, int, int, int, int, int]) -> None:
        self.values = values

    def one(self) -> tuple[int, int, int, int, int, int]:
        return self.values


class HealthSession:
    def __init__(self, values: tuple[int, int, int, int, int, int]) -> None:
        self.values = values

    async def execute(self, _: Any) -> AggregateResult:
        return AggregateResult(self.values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("values", "expected_status", "expected_ratio", "objective_met"),
    [
        ((2, 0, 2, 0, 0, 1), ModuleHealthStatus.HEALTHY, 1.0, True),
        ((4, 0, 3, 1, 0, 0), ModuleHealthStatus.DEGRADED, 0.75, False),
        ((2, 1, 0, 0, 1, 0), ModuleHealthStatus.UNAVAILABLE, 0.0, False),
        ((0, 0, 0, 0, 0, 0), ModuleHealthStatus.UNMONITORED, None, None),
    ],
)
async def test_module_health_summary_has_stable_operational_states(
    values: tuple[int, int, int, int, int, int],
    expected_status: ModuleHealthStatus,
    expected_ratio: float | None,
    objective_met: bool | None,
) -> None:
    observed_at = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
    summary = await summarize_module_health(
        cast(AsyncSession, HealthSession(values)),
        availability_target=0.99,
        lease_warning_seconds=30,
        now=observed_at,
    )

    assert summary.generated_at == observed_at
    assert summary.status is expected_status
    assert summary.availability_ratio == expected_ratio
    assert summary.objective_met is objective_met
    assert summary.monitored_modules == values[0]
    assert summary.at_risk_leases == values[5]
    assert sum(summary.counts.model_dump().values()) == values[0]
