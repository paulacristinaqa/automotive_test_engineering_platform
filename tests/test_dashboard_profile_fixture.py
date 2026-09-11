from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from tools.profile_dashboard_queries import _prepare_synthetic_components


class Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


@pytest.mark.asyncio
async def test_profile_fixture_writes_only_fixed_temporary_tables() -> None:
    connection = Connection()
    await _prepare_synthetic_components(cast(AsyncConnection, connection))
    assert len(connection.statements) == 6
    for statement in connection.statements[:3]:
        assert statement.startswith("CREATE TEMP TABLE ")
        assert "SELECT * FROM public." in statement
        assert statement.endswith("WITH NO DATA")
    for statement in connection.statements[3:]:
        assert statement.startswith("INSERT INTO pg_temp.")
        assert "public." not in statement
    assert "(20,80,-10,'normal')" in connection.statements[3]
