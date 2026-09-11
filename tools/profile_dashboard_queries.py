"""Small PostgreSQL read-only regression profile, not a fleet-scale load benchmark."""

from time import perf_counter
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from atep.dashboard.exports import ExportView, generate_export
from atep.dashboard.mobility import NumericDistribution, build_mobility_analytics
from atep.electric_vehicle.models import (
    BatteryPackState,
    MotorInverterState,
    ThermalManagementState,
)


async def profile_dashboard_queries(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://", 1))
    statements: list[str] = []

    def count_query(*args: Any) -> None:
        statements.append(str(args[2]).lstrip().split(None, 1)[0].upper())

    event.listen(engine.sync_engine, "before_cursor_execute", count_query)
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            await connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
            async with AsyncSession(bind=connection) as session:
                statements.clear()
                started = perf_counter()
                reference = []
                for column, metric, unit in (
                    (BatteryPackState.soc_pct, "battery_soc", "percent"),
                    (BatteryPackState.soh_pct, "battery_soh", "percent"),
                    (BatteryPackState.pack_temperature_c, "battery_temperature", "celsius"),
                    (MotorInverterState.motor_temperature_c, "motor_temperature", "celsius"),
                    (MotorInverterState.inverter_temperature_c, "inverter_temperature", "celsius"),
                    (ThermalManagementState.cabin_temperature_c, "cabin_temperature", "celsius"),
                ):
                    count, low, mean, high = (
                        await session.execute(
                            select(
                                func.count(column),
                                func.min(column),
                                func.avg(column),
                                func.max(column),
                            )
                        )
                    ).one()
                    reference.append(
                        NumericDistribution(
                            metric=metric,
                            unit=unit,
                            sample_count=count,
                            minimum=low,
                            average=mean,
                            maximum=high,
                        )
                    )
                reference_ms = (perf_counter() - started) * 1000
                assert statements == ["SELECT"] * 6
                statements.clear()
                started = perf_counter()
                current = await build_mobility_analytics(session, window_hours=24)
                current_ms = (perf_counter() - started) * 1000
                assert current.current_metrics == reference
                assert statements == ["SELECT"] * 10
                exported_sizes = {}
                for view in ("operations", "mobility", "evidence-readiness"):
                    export_view: ExportView = view
                    payload = await generate_export(session, view=export_view, window_hours=24)
                    exported_sizes[view] = len(payload)
                assert all(statement == "SELECT" for statement in statements)
                return {
                    "schema_version": "dashboard-query-profile-v1",
                    "status": "passed",
                    "transaction": "repeatable_read_read_only",
                    "reference_numeric_selects": 6,
                    "optimized_numeric_selects": 3,
                    "previous_total_selects": 13,
                    "optimized_total_selects": 10,
                    "reference_numeric_elapsed_ms": round(reference_ms, 3),
                    "optimized_full_view_elapsed_ms": round(current_ms, 3),
                    "metric_sample_counts": {item.metric: item.sample_count for item in reference},
                    "export_sizes_bytes": exported_sizes,
                    "limitations": [
                        "One small fixture run, not a latency SLA or fleet benchmark.",
                        "Numeric-only reference and full-view timings are not comparable speedups.",
                        "No source writes permitted; no source retention policy changed.",
                    ],
                }
    finally:
        await engine.dispose()
