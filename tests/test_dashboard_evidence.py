from datetime import timedelta
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from atep.dashboard.evidence import build_evidence_readiness


class Result:
    def __init__(self, rows: list[tuple[str, int]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[str, int]]:
        return self.rows


class Session:
    def __init__(self, empty: bool) -> None:
        self.rows = (
            [[], [], []] if empty else [[("completed", 10)], [("covered", 20)], [("success", 30)]]
        )
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Result:
        self.statements.append(statement)
        return Result(self.rows.pop(0))


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_evidence_never_infers_conformity_from_counts(empty: bool) -> None:
    session = Session(empty)
    result = await build_evidence_readiness(cast(AsyncSession, session), window_hours=24)
    assert result.assessment == "not_assessed"
    assert result.generated_at - result.window_start == timedelta(hours=24)
    assert [gap.area for gap in result.gaps] == ["ota", "cybersecurity", "aspice", "iso26262"]
    assert result.gaps[0].status == "not_implemented"
    assert all(gap.status == "not_assessed" for gap in result.gaps[1:])
    assert all(gap.missing_capabilities and gap.limitation for gap in result.gaps)
    assert sum(item.count for item in result.diagnostic_flash_states) == (0 if empty else 10)
    assert sum(item.count for item in result.requirement_coverage_states) == (0 if empty else 20)
    assert sum(item.count for item in result.audit_outcomes) == (0 if empty else 30)
    assert not session.rows
    assert all("WHERE" not in str(query) for query in session.statements[:2])
    query = session.statements[2]
    assert ">=" in str(query) and "<=" in str(query)
    assert result.window_start in query.compile().params.values()
    assert result.generated_at in query.compile().params.values()
    for query in session.statements:
        assert "ORDER BY" in str(query)
        assert not {"image_data", "details", "actor_user_id"} & {
            column.key for column in query.selected_columns
        }
