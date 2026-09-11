"""Read-only, chart-ready EV and ADAS projections; source models remain authoritative."""

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from atep.adas.models import AdasPlanningEvaluation, AdasTestScenarioExecution
from atep.dashboard.schemas import StatusCount
from atep.electric_vehicle.models import (
    BatteryPackState,
    ChargingSystemState,
    ElectricVehicleScenarioExecution,
    MotorInverterState,
    ThermalManagementState,
)


class NumericDistribution(BaseModel):
    metric: str
    unit: str
    sample_count: int = Field(ge=0)
    minimum: float | None
    average: float | None
    maximum: float | None


class MobilityAnalytics(BaseModel):
    generated_at: datetime
    window_start: datetime
    window_hours: int = Field(ge=1, le=720)
    current_metrics: list[NumericDistribution]
    battery_states: list[StatusCount]
    motor_states: list[StatusCount]
    charging_states: list[StatusCount]
    thermal_states: list[StatusCount]
    ev_scenario_outcomes: list[StatusCount]
    adas_scenario_outcomes: list[StatusCount]
    adas_maneuvers: list[StatusCount]
    contract_version: str = "dashboard-mobility-analytics-v1"
    limitations: list[str]


async def _distribution(
    session: AsyncSession, column: InstrumentedAttribute[float], *, metric: str, unit: str
) -> NumericDistribution:
    count, minimum, average, maximum = (
        await session.execute(
            select(func.count(column), func.min(column), func.avg(column), func.max(column))
        )
    ).one()
    return NumericDistribution(
        metric=metric,
        unit=unit,
        sample_count=int(count),
        minimum=float(minimum) if minimum is not None else None,
        average=float(average) if average is not None else None,
        maximum=float(maximum) if maximum is not None else None,
    )


async def _statuses(
    session: AsyncSession,
    column: InstrumentedAttribute[str],
    *,
    timestamp: InstrumentedAttribute[datetime] | None = None,
    start: datetime,
    end: datetime,
) -> list[StatusCount]:
    statement = select(column, func.count()).group_by(column).order_by(column)
    if timestamp is not None:
        statement = statement.where(timestamp >= start, timestamp <= end)
    return [
        StatusCount(status=status, count=count)
        for status, count in (await session.execute(statement)).all()
    ]


async def build_mobility_analytics(
    session: AsyncSession, *, window_hours: int
) -> MobilityAnalytics:
    now = datetime.now(UTC)
    start = now - timedelta(hours=window_hours)
    metrics = []
    for column, metric, unit in (
        (BatteryPackState.soc_pct, "battery_soc", "percent"),
        (BatteryPackState.soh_pct, "battery_soh", "percent"),
        (BatteryPackState.pack_temperature_c, "battery_temperature", "celsius"),
        (MotorInverterState.motor_temperature_c, "motor_temperature", "celsius"),
        (MotorInverterState.inverter_temperature_c, "inverter_temperature", "celsius"),
        (ThermalManagementState.cabin_temperature_c, "cabin_temperature", "celsius"),
    ):
        metrics.append(await _distribution(session, column, metric=metric, unit=unit))
    groups = []
    for status_column, timestamp in (
        (BatteryPackState.operating_state, None),
        (MotorInverterState.operating_state, None),
        (ChargingSystemState.operating_state, None),
        (ThermalManagementState.operating_state, None),
        (ElectricVehicleScenarioExecution.status, ElectricVehicleScenarioExecution.created_at),
        (AdasTestScenarioExecution.status, AdasTestScenarioExecution.created_at),
        (AdasPlanningEvaluation.maneuver, AdasPlanningEvaluation.created_at),
    ):
        groups.append(
            await _statuses(session, status_column, timestamp=timestamp, start=start, end=now)
        )
    return MobilityAnalytics(
        generated_at=now,
        window_start=start,
        window_hours=window_hours,
        current_metrics=metrics,
        battery_states=groups[0],
        motor_states=groups[1],
        charging_states=groups[2],
        thermal_states=groups[3],
        ev_scenario_outcomes=groups[4],
        adas_scenario_outcomes=groups[5],
        adas_maneuvers=groups[6],
        limitations=[
            "Metrics and states describe stored simulation records, not live health.",
            "Averages are unweighted per stored component; missing components are excluded.",
            "Scenario outcomes and planning maneuvers use the inclusive server-time UTC window.",
            "Maneuver counts describe planning evaluations, not actual vehicle maneuvers.",
            "Sequential reads are not an atomic snapshot or safety certification evidence.",
        ],
    )
