from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.integration_service import (
    create_integration_evidence,
    integration_evidence_response,
    require_integration_evidence,
)
from atep.adas.perception_service import (
    create_perception_result,
    perception_response,
    require_perception_result,
)
from atep.adas.planning_service import (
    create_planning_evaluation,
    planning_response,
    require_planning_evaluation,
)
from atep.adas.scenario_service import (
    execute_scenario,
    list_scenario_executions,
    require_scenario_execution,
    scenario_response,
)
from atep.adas.schemas import (
    AdasIntegrationEvidenceCreate,
    AdasIntegrationEvidenceResponse,
    AdasScenarioExecute,
    AdasScenarioPage,
    AdasScenarioResponse,
    AdasTestRunEvidenceStreamEvent,
    PerceptionResultCreate,
    PerceptionResultResponse,
    PlanningEvaluationCreate,
    PlanningEvaluationResponse,
    SensorConfigurationCreate,
    SensorConfigurationPage,
    SensorConfigurationResponse,
    SensorObservationCreate,
    SensorObservationResponse,
    WorldSceneAdvance,
    WorldSceneContextUpdate,
    WorldSceneCreate,
    WorldScenePage,
    WorldSceneResponse,
)
from atep.adas.sensor_service import (
    capture_observation,
    create_sensor,
    list_sensors,
    observation_response,
    require_observation,
    require_sensor,
    sensor_response,
)
from atep.adas.service import (
    advance_scene,
    create_scene,
    list_scenes,
    require_scene,
    scene_response,
    update_scene_context,
)
from atep.core.errors import ResourceNotFoundError
from atep.db.session import get_session
from atep.identity.dependencies import require_permissions
from atep.identity.models import User
from atep.identity.permissions import PermissionName
from atep.identity.users_router import request_correlation_id
from atep.test_runs.models import TestRun
from atep.test_runs.realtime import publish_test_run_message
from atep.test_runs.service import require_test_run
from atep.vehicles.models import VehicleCommand, VehicleTelemetryEvent
from atep.vehicles.service import require_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/adas/scenes", tags=["adas"])
adas_read = require_permissions(PermissionName.ADAS_READ.value)
adas_manage = require_permissions(PermissionName.ADAS_MANAGE.value)


@router.post("", response_model=WorldSceneResponse, status_code=status.HTTP_201_CREATED)
async def create_scene_endpoint(
    vehicle_id: str,
    command: WorldSceneCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await create_scene(
        session,
        vehicle=vehicle,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(scene, attribute_names=["created_at", "updated_at"])
    return scene_response(scene, vehicle)


@router.get("", response_model=WorldScenePage)
async def list_scenes_endpoint(
    vehicle_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> WorldScenePage:
    vehicle = await require_vehicle(session, vehicle_id)
    scenes, total = await list_scenes(session, vehicle_id=vehicle.id, limit=limit, offset=offset)
    return WorldScenePage(
        items=[scene_response(item, vehicle) for item in scenes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{scene_id}", response_model=WorldSceneResponse)
async def get_scene_endpoint(
    vehicle_id: str,
    scene_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    return scene_response(
        await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id), vehicle
    )


@router.post("/{scene_id}/advance", response_model=WorldSceneResponse)
async def advance_scene_endpoint(
    vehicle_id: str,
    scene_id: str,
    command: WorldSceneAdvance,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    await advance_scene(
        session,
        scene=scene,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(scene, attribute_names=["updated_at"])
    return scene_response(scene, vehicle)


@router.patch("/{scene_id}/context", response_model=WorldSceneResponse)
async def update_scene_context_endpoint(
    vehicle_id: str,
    scene_id: str,
    command: WorldSceneContextUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> WorldSceneResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    await update_scene_context(
        session,
        scene=scene,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(scene, attribute_names=["updated_at"])
    return scene_response(scene, vehicle)


@router.post(
    "/{scene_id}/sensors",
    response_model=SensorConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sensor_endpoint(
    vehicle_id: str,
    scene_id: str,
    command: SensorConfigurationCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> SensorConfigurationResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await create_sensor(
        session,
        scene=scene,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(sensor, attribute_names=["created_at", "updated_at"])
    return sensor_response(sensor, scene)


@router.get("/{scene_id}/sensors", response_model=SensorConfigurationPage)
async def list_sensors_endpoint(
    vehicle_id: str,
    scene_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> SensorConfigurationPage:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensors, total = await list_sensors(session, scene_id=scene.id, limit=limit, offset=offset)
    return SensorConfigurationPage(
        items=[sensor_response(item, scene) for item in sensors],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{scene_id}/sensors/{sensor_id}/observations",
    response_model=SensorObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def capture_sensor_observation_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    command: SensorObservationCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> SensorObservationResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await capture_observation(
        session,
        scene=scene,
        sensor=sensor,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(observation, attribute_names=["created_at"])
    return observation_response(observation, sensor, scene)


@router.get(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}",
    response_model=SensorObservationResponse,
)
async def get_sensor_observation_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
) -> SensorObservationResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    return observation_response(observation, sensor, scene)


@router.post(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results",
    response_model=PerceptionResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_perception_result_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    command: PerceptionResultCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> PerceptionResultResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    result = await create_perception_result(
        session,
        scene=scene,
        observation=observation,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(result, attribute_names=["created_at"])
    return perception_response(result, observation, scene)


@router.get(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/{result_id}",
    response_model=PerceptionResultResponse,
)
async def get_perception_result_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    result_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
) -> PerceptionResultResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    result = await require_perception_result(
        session, observation_id=observation.id, result_id=result_id
    )
    return perception_response(result, observation, scene)


@router.post(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/"
    "{result_id}/planning-evaluations",
    response_model=PlanningEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_planning_evaluation_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    result_id: str,
    command: PlanningEvaluationCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> PlanningEvaluationResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    perception = await require_perception_result(
        session, observation_id=observation.id, result_id=result_id
    )
    evaluation = await create_planning_evaluation(
        session,
        scene=scene,
        perception=perception,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    await session.refresh(evaluation, attribute_names=["created_at"])
    return planning_response(evaluation, perception, scene)


@router.get(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/"
    "{result_id}/planning-evaluations/{evaluation_id}",
    response_model=PlanningEvaluationResponse,
)
async def get_planning_evaluation_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    result_id: str,
    evaluation_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
) -> PlanningEvaluationResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    perception = await require_perception_result(
        session, observation_id=observation.id, result_id=result_id
    )
    evaluation = await require_planning_evaluation(
        session, perception_result_id=perception.id, evaluation_id=evaluation_id
    )
    return planning_response(evaluation, perception, scene)


@router.post(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/"
    "{result_id}/test-scenarios",
    response_model=AdasScenarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_adas_scenario_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    result_id: str,
    command: AdasScenarioExecute,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> AdasScenarioResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    perception = await require_perception_result(
        session, observation_id=observation.id, result_id=result_id
    )
    execution, duplicate = await execute_scenario(
        session,
        scene=scene,
        perception=perception,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if not duplicate:
        await session.refresh(execution, attribute_names=["created_at"])
    return scenario_response(
        execution, scene=scene, perception=perception, duplicate=duplicate
    )


@router.get(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/"
    "{result_id}/test-scenarios",
    response_model=AdasScenarioPage,
)
async def list_adas_scenarios_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    result_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> AdasScenarioPage:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    perception = await require_perception_result(
        session, observation_id=observation.id, result_id=result_id
    )
    items, total = await list_scenario_executions(
        session,
        scene_id=scene.id,
        perception_result_id=perception.id,
        limit=limit,
        offset=offset,
    )
    return AdasScenarioPage(
        items=[scenario_response(item, scene=scene, perception=perception) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/"
    "{result_id}/test-scenarios/{execution_id}",
    response_model=AdasScenarioResponse,
)
async def get_adas_scenario_endpoint(
    vehicle_id: str,
    scene_id: str,
    sensor_id: str,
    observation_id: str,
    result_id: str,
    execution_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
) -> AdasScenarioResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    sensor = await require_sensor(session, scene_id=scene.id, sensor_id=sensor_id)
    observation = await require_observation(
        session, sensor_id=sensor.id, observation_id=observation_id
    )
    perception = await require_perception_result(
        session, observation_id=observation.id, result_id=result_id
    )
    execution = await require_scenario_execution(
        session, scene_id=scene.id, execution_id=execution_id
    )
    if execution.perception_result_id != perception.id:
        raise ResourceNotFoundError("adas_test_scenario")
    return scenario_response(execution, scene=scene, perception=perception)


@router.post(
    "/{scene_id}/test-scenarios/{execution_id}/integration-evidence",
    response_model=AdasIntegrationEvidenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_adas_integration_evidence_endpoint(
    vehicle_id: str,
    scene_id: str,
    execution_id: str,
    command: AdasIntegrationEvidenceCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(adas_manage)],
) -> AdasIntegrationEvidenceResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    scenario = await require_scenario_execution(
        session, scene_id=scene.id, execution_id=execution_id
    )
    test_run, _test_run_vehicle = await require_test_run(session, command.test_run_id)
    telemetry_events = list(
        await session.scalars(
            select(VehicleTelemetryEvent).where(
                VehicleTelemetryEvent.event_id.in_(command.telemetry_event_ids)
            )
        )
    )
    vehicle_commands = list(
        await session.scalars(
            select(VehicleCommand).where(
                VehicleCommand.command_id.in_(command.vehicle_command_ids)
            )
        )
    )
    evidence, duplicate = await create_integration_evidence(
        session,
        scene=scene,
        scenario=scenario,
        test_run=test_run,
        telemetry_events=telemetry_events,
        vehicle_commands=vehicle_commands,
        command=command,
        actor_user_id=actor.id,
        correlation_id=request_correlation_id(request),
    )
    await session.commit()
    if not duplicate:
        await session.refresh(evidence, attribute_names=["created_at"])
    response = integration_evidence_response(
        evidence,
        scene=scene,
        scenario=scenario,
        test_run=test_run,
        duplicate=duplicate,
    )
    if not duplicate:
        stream_event = AdasTestRunEvidenceStreamEvent(
            run_id=test_run.run_id,
            evidence_id=response.evidence_id,
            scenario_execution_id=response.scenario_execution_id,
            dashboard_summary=response.dashboard_summary,
            occurred_at=datetime.now(UTC),
        )
        await publish_test_run_message(
            request.app.state.redis,
            run_id=test_run.run_id,
            event=stream_event,
            event_type=stream_event.type,
            observability=request.app.state.observability,
        )
    return response


@router.get(
    "/{scene_id}/test-scenarios/{execution_id}/integration-evidence",
    response_model=AdasIntegrationEvidenceResponse,
)
async def get_adas_integration_evidence_endpoint(
    vehicle_id: str,
    scene_id: str,
    execution_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[User, Depends(adas_read)],
) -> AdasIntegrationEvidenceResponse:
    vehicle = await require_vehicle(session, vehicle_id)
    scene = await require_scene(session, vehicle_id=vehicle.id, scene_id=scene_id)
    scenario = await require_scenario_execution(
        session, scene_id=scene.id, execution_id=execution_id
    )
    evidence = await require_integration_evidence(
        session, scenario_execution_id=scenario.id
    )
    test_run = await session.get(TestRun, evidence.test_run_id)
    if test_run is None:
        raise ResourceNotFoundError("test_run")
    return integration_evidence_response(
        evidence, scene=scene, scenario=scenario, test_run=test_run
    )
