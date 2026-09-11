from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atep.dashboard.mobility import build_mobility_analytics


class Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def one(self) -> Any:
        return self.value

    def all(self) -> Any:
        return self.value


class Session:
    def __init__(self, empty: bool) -> None:
        self.rows: list[Any] = (
            [(0, None, None, None) * size for size in (3, 2, 1)] + [[]] * 7
            if empty
            else [(2, 20.0, 45.0, 70.0) * size for size in (3, 2, 1)]
            + [[("normal", 2)]] * 4
            + [[("passed", 3)], [("failed", 1)], [("stop", 2)]]
        )
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Result:
        self.statements.append(statement)
        return Result(self.rows.pop(0))


@pytest.mark.asyncio
async def test_grouped_metrics_preserve_distinct_populations_and_nulls() -> None:
    session = Session(True)
    session.rows = [
        (2, 10.0, 30.0, 50.0, 2, 80.0, 90.0, 100.0, 2, -10.0, 0.0, 10.0),
        (1, 42.0, 42.0, 42.0, 1, 55.0, 55.0, 55.0),
        (0, None, None, None),
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    ]
    result = await build_mobility_analytics(cast(AsyncSession, session), window_hours=24)
    assert [item.sample_count for item in result.current_metrics] == [2, 2, 2, 1, 1, 0]
    assert [item.average for item in result.current_metrics] == [30.0, 90.0, 0.0, 42.0, 55.0, None]
    assert result.current_metrics[2].minimum == -10.0
    assert result.current_metrics[1].maximum == 100.0
    assert result.current_metrics[-1].minimum is None


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [True, False])
async def test_mobility_distributions_and_truthful_empty_state(empty: bool) -> None:
    session = Session(empty)
    result = await build_mobility_analytics(cast(AsyncSession, session), window_hours=24)
    assert result.generated_at - result.window_start == timedelta(hours=24)
    assert result.contract_version == "dashboard-mobility-analytics-v1"
    assert len(result.current_metrics) == 6
    assert [item.metric for item in result.current_metrics] == [
        "battery_soc",
        "battery_soh",
        "battery_temperature",
        "motor_temperature",
        "inverter_temperature",
        "cabin_temperature",
    ]
    for item in result.current_metrics:
        assert item.sample_count == (0 if empty else 2)
        assert item.minimum == (None if empty else 20.0)
        assert item.average == (None if empty else 45.0)
        assert item.maximum == (None if empty else 70.0)
    assert sum(item.count for item in result.adas_scenario_outcomes) == (0 if empty else 1)
    assert sum(item.count for item in result.ev_scenario_outcomes) == (0 if empty else 3)
    assert sum(item.count for item in result.adas_maneuvers) == (0 if empty else 2)
    assert not session.rows
    assert len(session.statements) == 10
    assert all(len(statement.get_final_froms()) == 1 for statement in session.statements)
    assert all("WHERE" not in str(statement) for statement in session.statements[:7])
    for statement in session.statements[7:]:
        sql = str(statement)
        assert ">=" in sql and "<=" in sql and "ORDER BY" in sql
        parameters = statement.compile().params.values()
        assert result.window_start in parameters
        assert result.generated_at in parameters
    assert all(" JOIN " not in str(statement) for statement in session.statements)
