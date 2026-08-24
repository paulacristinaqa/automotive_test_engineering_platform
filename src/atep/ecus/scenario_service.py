import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import EcuScenarioExecutionConflictError, ResourceNotFoundError
from atep.ecus.models import (
    EcuScenarioExecution,
    EcuSignalRoute,
    ElectronicControlUnit,
)
from atep.ecus.schemas import (
    EcuAdvanceCommand,
    EcuFaultObservationCommand,
    EcuMemoryCorruptionCommand,
    EcuScenarioAction,
    EcuScenarioActionKind,
    EcuScenarioActionResult,
    EcuScenarioClockDiagnostic,
    EcuScenarioExecuteCommand,
    EcuScenarioExecutionResponse,
    EcuScenarioResourceMetrics,
    EcuScenarioTimingDiagnostics,
    EcuSignalPublishCommand,
    EcuSignalRouteTransferCommand,
)
from atep.ecus.service import (
    corrupt_ecu_memory,
    execute_ecu_advance,
    observe_ecu_fault,
    publish_ecu_signal,
    require_ecu,
    transfer_signal_route,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def _request_hash(command: EcuScenarioExecuteCommand) -> str:
    payload = command.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


async def _vehicle_ecus(
    session: AsyncSession, *, vehicle: Vehicle
) -> list[ElectronicControlUnit]:
    result = await session.execute(
        select(ElectronicControlUnit)
        .where(ElectronicControlUnit.vehicle_id == vehicle.id)
        .order_by(ElectronicControlUnit.identifier)
    )
    return list(result.scalars().all())


async def _resource_metrics(
    session: AsyncSession, *, vehicle: Vehicle
) -> EcuScenarioResourceMetrics:
    ecus = await _vehicle_ecus(session, vehicle=vehicle)
    ecu_ids = [ecu.id for ecu in ecus]
    route_count = 0
    if ecu_ids:
        route_count = int(
            await session.scalar(
                select(func.count())
                .select_from(EcuSignalRoute)
                .where(EcuSignalRoute.gateway_ecu_id.in_(ecu_ids))
            )
            or 0
        )
    return EcuScenarioResourceMetrics(
        ecu_count=len(ecus),
        memory_cell_count=sum(len(ecu.memory) for ecu in ecus),
        signal_count=sum(len(ecu.signals or []) for ecu in ecus),
        active_fault_count=sum(
            sum(bool(fault.get("active")) for fault in ecu.faults) for ecu in ecus
        ),
        route_count=route_count,
        aggregate_version=sum(ecu.version for ecu in ecus),
    )


async def _timing_diagnostics(
    session: AsyncSession, *, vehicle: Vehicle
) -> EcuScenarioTimingDiagnostics:
    ecus = await _vehicle_ecus(session, vehicle=vehicle)
    if not ecus:
        return EcuScenarioTimingDiagnostics(
            minimum_time_ms=0,
            maximum_time_ms=0,
            clock_skew_ms=0,
            synchronized=True,
            ecus=[],
        )
    maximum = max(ecu.simulation_time_ms for ecu in ecus)
    minimum = min(ecu.simulation_time_ms for ecu in ecus)
    return EcuScenarioTimingDiagnostics(
        minimum_time_ms=minimum,
        maximum_time_ms=maximum,
        clock_skew_ms=maximum - minimum,
        synchronized=maximum == minimum,
        ecus=[
            EcuScenarioClockDiagnostic(
                ecu_id=ecu.identifier,
                simulation_time_ms=ecu.simulation_time_ms,
                lag_from_max_ms=maximum - ecu.simulation_time_ms,
            )
            for ecu in ecus[:16]
        ],
    )


def _command_id(execution_id: str, iteration: int, action_index: int) -> str:
    return f"scn-{execution_id}-{iteration}-{action_index}"


def _campaign_seed(base_seed: int, iteration: int, action_index: int) -> int:
    digest = hashlib.sha256(f"{base_seed}:{iteration}:{action_index}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 2_147_483_648


async def _require_route_by_identifier(
    session: AsyncSession, *, gateway: ElectronicControlUnit, identifier: str
) -> EcuSignalRoute:
    route = await session.scalar(
        select(EcuSignalRoute).where(
            EcuSignalRoute.gateway_ecu_id == gateway.id,
            EcuSignalRoute.identifier == identifier,
        )
    )
    if route is None:
        raise ResourceNotFoundError("ecu signal route")
    return route


async def _execute_action(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    action: EcuScenarioAction,
    iteration: int,
    action_index: int,
    execution_id: str,
    base_seed: int,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> EcuScenarioActionResult:
    command_id = _command_id(execution_id, iteration, action_index)
    target_identifier = action.ecu_id or action.gateway_ecu_id
    assert target_identifier is not None
    ecu = await require_ecu(session, vehicle=vehicle, identifier=target_identifier)
    outcome = "completed"
    state_version = ecu.version
    simulation_time_ms = ecu.simulation_time_ms

    if action.kind is EcuScenarioActionKind.ADVANCE_TIME:
        assert action.duration_ms is not None
        execution, _ = await execute_ecu_advance(
            session,
            vehicle=vehicle,
            ecu=ecu,
            command=EcuAdvanceCommand(
                command_id=command_id,
                expected_version=ecu.version,
                duration_ms=action.duration_ms,
            ),
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        state_version = execution.state_version
        simulation_time_ms = execution.simulation_time_ms
        outcome = "advanced"
    elif action.kind is EcuScenarioActionKind.OBSERVE_FAULT:
        assert action.fault_code is not None
        assert action.severity is not None
        assert action.detected is not None
        execution, _ = await observe_ecu_fault(
            session,
            vehicle=vehicle,
            ecu=ecu,
            command=EcuFaultObservationCommand(
                command_id=command_id,
                expected_version=ecu.version,
                code=action.fault_code,
                severity=action.severity,
                detected=action.detected,
                description=action.description,
                confirmation_threshold=action.confirmation_threshold,
                healing_threshold=action.healing_threshold,
                latched=action.latched,
            ),
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        state_version = execution.state_version
        simulation_time_ms = execution.simulation_time_ms
        outcome = str(execution.result["transition"])
    elif action.kind is EcuScenarioActionKind.CORRUPT_MEMORY:
        assert action.bit_flips is not None
        execution, _ = await corrupt_ecu_memory(
            session,
            vehicle=vehicle,
            ecu=ecu,
            command=EcuMemoryCorruptionCommand(
                command_id=command_id,
                expected_version=ecu.version,
                seed=_campaign_seed(base_seed, iteration, action_index),
                bit_flips=action.bit_flips,
                region_names=action.region_names,
            ),
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        state_version = execution.state_version
        simulation_time_ms = execution.simulation_time_ms
        outcome = "corrupted"
    elif action.kind is EcuScenarioActionKind.PUBLISH_SIGNAL:
        assert action.signal_name is not None
        assert action.value is not None
        execution, _ = await publish_ecu_signal(
            session,
            vehicle=vehicle,
            ecu=ecu,
            signal_name=action.signal_name,
            command=EcuSignalPublishCommand(
                command_id=command_id,
                expected_version=ecu.version,
                value=action.value,
            ),
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        state_version = execution.state_version
        simulation_time_ms = execution.simulation_time_ms
        outcome = "published"
    else:
        assert action.route_id is not None
        route = await _require_route_by_identifier(
            session, gateway=ecu, identifier=action.route_id
        )
        source = await session.get(ElectronicControlUnit, route.source_ecu_id)
        target = await session.get(ElectronicControlUnit, route.target_ecu_id)
        if source is None or target is None:
            raise ResourceNotFoundError("ecu")
        execution, _, _, target = await transfer_signal_route(
            session,
            vehicle=vehicle,
            gateway=ecu,
            route=route,
            command=EcuSignalRouteTransferCommand(
                command_id=command_id,
                expected_source_version=source.version,
                expected_target_version=target.version,
            ),
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )
        target_identifier = target.identifier
        state_version = execution.state_version
        simulation_time_ms = target.simulation_time_ms
        outcome = "transferred"

    return EcuScenarioActionResult(
        iteration=iteration,
        action_index=action_index,
        kind=action.kind,
        ecu_id=target_identifier,
        state_version=state_version,
        simulation_time_ms=simulation_time_ms,
        outcome=outcome,
    )


async def execute_scenario(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: EcuScenarioExecuteCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[EcuScenarioExecution, bool]:
    request_hash = _request_hash(command)
    locked_vehicle = await session.scalar(
        select(Vehicle).where(Vehicle.id == vehicle.id).with_for_update()
    )
    if locked_vehicle is None:
        raise ResourceNotFoundError("vehicle")
    existing = await session.scalar(
        select(EcuScenarioExecution).where(
            EcuScenarioExecution.vehicle_id == vehicle.id,
            EcuScenarioExecution.execution_id == command.execution_id,
        )
    )
    if existing is not None:
        if existing.request_hash == request_hash:
            return existing, True
        raise EcuScenarioExecutionConflictError()

    resources_before = await _resource_metrics(session, vehicle=vehicle)
    action_results: list[EcuScenarioActionResult] = []
    for iteration in range(1, command.iterations + 1):
        for action_index, action in enumerate(command.actions, start=1):
            action_results.append(
                await _execute_action(
                    session,
                    vehicle=vehicle,
                    action=action,
                    iteration=iteration,
                    action_index=action_index,
                    execution_id=command.execution_id,
                    base_seed=command.base_seed,
                    actor_user_id=actor_user_id,
                    correlation_id=correlation_id,
                )
            )
    resources_after = await _resource_metrics(session, vehicle=vehicle)
    timing = await _timing_diagnostics(session, vehicle=vehicle)
    result = {
        "resources_before": resources_before.model_dump(mode="json"),
        "resources_after": resources_after.model_dump(mode="json"),
        "timing": timing.model_dump(mode="json"),
        "actions": [item.model_dump(mode="json") for item in action_results],
    }
    scenario = EcuScenarioExecution(
        vehicle_id=vehicle.id,
        execution_id=command.execution_id,
        request_hash=request_hash,
        request=command.model_dump(mode="json"),
        result=result,
        iteration_count=command.iterations,
        requested_by_user_id=actor_user_id,
    )
    session.add(scenario)
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "scenario_execution_id": str(scenario.id),
        "execution_id": scenario.execution_id,
        "iteration_count": scenario.iteration_count,
        "action_count": len(action_results),
        "ecu_count": resources_after.ecu_count,
        "clock_skew_ms": timing.clock_skew_ms,
        "synchronized": timing.synchronized,
    }
    enqueue_event(
        session,
        event_type="atep.ecu.scenario.completed.v1",
        aggregate_type="ecu_scenario",
        aggregate_id=scenario.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="ecu.scenario_completed",
        resource_type="ecu_scenario",
        resource_id=scenario.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return scenario, False


async def require_scenario_execution(
    session: AsyncSession, *, vehicle: Vehicle, execution_id: str
) -> EcuScenarioExecution:
    scenario = await session.scalar(
        select(EcuScenarioExecution).where(
            EcuScenarioExecution.vehicle_id == vehicle.id,
            EcuScenarioExecution.execution_id == execution_id,
        )
    )
    if scenario is None:
        raise ResourceNotFoundError("ecu scenario execution")
    return scenario


async def list_scenario_executions(
    session: AsyncSession, *, vehicle: Vehicle, limit: int, offset: int
) -> tuple[list[EcuScenarioExecution], int]:
    query = select(EcuScenarioExecution).where(EcuScenarioExecution.vehicle_id == vehicle.id)
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    result = await session.execute(
        query.order_by(EcuScenarioExecution.created_at.desc(), EcuScenarioExecution.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


def scenario_response(
    scenario: EcuScenarioExecution, *, vehicle: Vehicle, duplicate: bool = False
) -> EcuScenarioExecutionResponse:
    request = EcuScenarioExecuteCommand.model_validate(scenario.request)
    return EcuScenarioExecutionResponse(
        id=scenario.id,
        execution_id=scenario.execution_id,
        vehicle_id=vehicle.identifier,
        iterations=scenario.iteration_count,
        base_seed=request.base_seed,
        action_count=len(scenario.result["actions"]),
        duplicate=duplicate,
        resources_before=EcuScenarioResourceMetrics.model_validate(
            scenario.result["resources_before"]
        ),
        resources_after=EcuScenarioResourceMetrics.model_validate(
            scenario.result["resources_after"]
        ),
        timing=EcuScenarioTimingDiagnostics.model_validate(scenario.result["timing"]),
        actions=[
            EcuScenarioActionResult.model_validate(item) for item in scenario.result["actions"]
        ],
        created_at=scenario.created_at,
    )
