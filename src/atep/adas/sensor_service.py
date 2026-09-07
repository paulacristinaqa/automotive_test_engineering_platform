import math
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasSensorConfiguration, AdasSensorObservation, AdasWorldScene
from atep.adas.schemas import (
    EnvironmentConditions,
    SensorConfigurationCreate,
    SensorConfigurationResponse,
    SensorDetection,
    SensorObservationCreate,
    SensorObservationResponse,
    Vector3,
    WorldActor,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AdasObservationConflictError,
    AdasSceneContractError,
    AdasSceneVersionConflictError,
    AdasSensorConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event


def sensor_response(
    sensor: AdasSensorConfiguration, scene: AdasWorldScene
) -> SensorConfigurationResponse:
    return SensorConfigurationResponse(
        id=sensor.id,
        scene_id=scene.scene_id,
        sensor_id=sensor.sensor_id,
        sensor_type=sensor.sensor_type,
        mount_position_m=sensor.mount_position,
        yaw_deg=sensor.yaw_deg,
        max_range_m=sensor.max_range_m,
        horizontal_fov_deg=sensor.horizontal_fov_deg,
        latency_ms=sensor.latency_ms,
        position_noise_stddev_m=sensor.position_noise_stddev_m,
        created_by_user_id=sensor.created_by_user_id,
        created_at=sensor.created_at,
        updated_at=sensor.updated_at,
    )


def observation_response(
    observation: AdasSensorObservation, sensor: AdasSensorConfiguration, scene: AdasWorldScene
) -> SensorObservationResponse:
    return SensorObservationResponse(
        id=observation.id,
        observation_id=observation.observation_id,
        scene_id=scene.scene_id,
        sensor_id=sensor.sensor_id,
        sensor_type=sensor.sensor_type,
        scene_revision=observation.scene_revision,
        scene_simulation_time_ms=observation.scene_simulation_time_ms,
        observed_simulation_time_ms=observation.observed_simulation_time_ms,
        seed=observation.seed,
        detections=observation.detections,
        metrics=observation.metrics,
        requested_by_user_id=observation.requested_by_user_id,
        created_at=observation.created_at,
    )


async def create_sensor(
    session: AsyncSession,
    *,
    scene: AdasWorldScene,
    command: SensorConfigurationCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> AdasSensorConfiguration:
    sensor = AdasSensorConfiguration(
        scene_id=scene.id,
        sensor_id=command.sensor_id,
        sensor_type=command.sensor_type.value,
        mount_position=command.mount_position_m.model_dump(mode="json"),
        yaw_deg=command.yaw_deg,
        max_range_m=command.max_range_m,
        horizontal_fov_deg=command.horizontal_fov_deg,
        latency_ms=command.latency_ms,
        position_noise_stddev_m=command.position_noise_stddev_m,
        created_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(sensor)
            await session.flush()
    except IntegrityError as exc:
        raise AdasSensorConflictError() from exc
    evidence = {
        "scene_id": scene.scene_id,
        "sensor_id": sensor.sensor_id,
        "sensor_type": sensor.sensor_type,
        "max_range_m": sensor.max_range_m,
        "horizontal_fov_deg": sensor.horizontal_fov_deg,
    }
    enqueue_event(
        session,
        event_type="atep.adas.sensor.created.v1",
        aggregate_type="adas_sensor",
        aggregate_id=sensor.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.sensor_created",
        resource_type="adas_sensor",
        resource_id=sensor.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return sensor


async def list_sensors(
    session: AsyncSession, *, scene_id: UUID, limit: int, offset: int
) -> tuple[list[AdasSensorConfiguration], int]:
    base = select(AdasSensorConfiguration).where(AdasSensorConfiguration.scene_id == scene_id)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    result = await session.execute(
        base.order_by(AdasSensorConfiguration.created_at.desc(), AdasSensorConfiguration.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def require_sensor(
    session: AsyncSession, *, scene_id: UUID, sensor_id: str
) -> AdasSensorConfiguration:
    sensor = await session.scalar(
        select(AdasSensorConfiguration).where(
            AdasSensorConfiguration.scene_id == scene_id,
            AdasSensorConfiguration.sensor_id == sensor_id,
        )
    )
    if sensor is None:
        raise ResourceNotFoundError("adas_sensor")
    return sensor


async def require_observation(
    session: AsyncSession, *, sensor_id: UUID, observation_id: str
) -> AdasSensorObservation:
    observation = await session.scalar(
        select(AdasSensorObservation).where(
            AdasSensorObservation.sensor_configuration_id == sensor_id,
            AdasSensorObservation.observation_id == observation_id,
        )
    )
    if observation is None:
        raise ResourceNotFoundError("adas_sensor_observation")
    return observation


async def capture_observation(
    session: AsyncSession,
    *,
    scene: AdasWorldScene,
    sensor: AdasSensorConfiguration,
    command: SensorObservationCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> AdasSensorObservation:
    if scene.revision != command.expected_scene_revision:
        raise AdasSceneVersionConflictError(
            expected=command.expected_scene_revision, actual=scene.revision
        )
    detections, metrics = simulate_detections(scene=scene, sensor=sensor, seed=command.seed)
    observation = AdasSensorObservation(
        sensor_configuration_id=sensor.id,
        observation_id=command.observation_id,
        scene_revision=scene.revision,
        scene_simulation_time_ms=scene.simulation_time_ms,
        observed_simulation_time_ms=max(0, scene.simulation_time_ms - sensor.latency_ms),
        seed=command.seed,
        detections=[item.model_dump(mode="json") for item in detections],
        metrics=metrics,
        requested_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(observation)
            await session.flush()
    except IntegrityError as exc:
        raise AdasObservationConflictError() from exc
    evidence = {
        "scene_id": scene.scene_id,
        "sensor_id": sensor.sensor_id,
        "observation_id": observation.observation_id,
        "scene_revision": scene.revision,
        "detection_count": len(detections),
        "seed": command.seed,
        "observed_simulation_time_ms": observation.observed_simulation_time_ms,
    }
    enqueue_event(
        session,
        event_type="atep.adas.sensor.observation.created.v1",
        aggregate_type="adas_sensor_observation",
        aggregate_id=observation.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.sensor_observation_created",
        resource_type="adas_sensor_observation",
        resource_id=observation.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return observation


def simulate_detections(
    *, scene: AdasWorldScene, sensor: AdasSensorConfiguration, seed: int
) -> tuple[list[SensorDetection], dict[str, int | float]]:
    actors = [WorldActor.model_validate(item) for item in scene.actors]
    ego = next((item for item in actors if item.actor_type.value == "ego_vehicle"), None)
    if ego is None:
        raise AdasSceneContractError("The scene requires an ego vehicle for sensor simulation.")
    mount = Vector3.model_validate(sensor.mount_position)
    heading = math.radians(ego.heading_deg)
    origin_x = ego.position_m.x + mount.x * math.cos(heading) - mount.y * math.sin(heading)
    origin_y = ego.position_m.y + mount.x * math.sin(heading) + mount.y * math.cos(heading)
    origin_z = ego.position_m.z + mount.z
    sensor_heading = _normalize_angle(ego.heading_deg + sensor.yaw_deg)
    environment = EnvironmentConditions.model_validate(scene.environment)
    effective_range = min(sensor.max_range_m, environment.visibility_m)
    candidates: list[tuple[float, float, float, float, WorldActor]] = []
    for actor in actors:
        if actor.actor_id == ego.actor_id:
            continue
        dx, dy, dz = (
            actor.position_m.x - origin_x,
            actor.position_m.y - origin_y,
            actor.position_m.z - origin_z,
        )
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        azimuth = _normalize_angle(math.degrees(math.atan2(dy, dx)) - sensor_heading)
        if distance <= effective_range and abs(azimuth) <= sensor.horizontal_fov_deg / 2:
            half_width = math.degrees(math.atan2(actor.width_m / 2, max(distance, 0.001)))
            candidates.append((distance, azimuth, half_width, dz, actor))
    candidates.sort(key=lambda item: (item[0], item[4].actor_id))
    visible: list[tuple[float, float, float, float, WorldActor]] = []
    occluded = 0
    for candidate in candidates:
        _, azimuth, half_width, _, _ = candidate
        if any(
            abs(_normalize_angle(azimuth - near[1])) <= max(0.25, near[2] - half_width * 0.25)
            for near in visible
        ):
            occluded += 1
            continue
        visible.append(candidate)
    detections = [
        _detection(item, sensor=sensor, environment=environment, seed=seed) for item in visible
    ]
    metrics: dict[str, int | float] = {
        "candidate_count": len(candidates),
        "detection_count": len(detections),
        "occluded_count": occluded,
        "effective_range_m": round(effective_range, 3),
    }
    return detections, metrics


def _detection(
    candidate: tuple[float, float, float, float, WorldActor],
    *,
    sensor: AdasSensorConfiguration,
    environment: EnvironmentConditions,
    seed: int,
) -> SensorDetection:
    distance, azimuth, _, relative_z, actor = candidate
    noise_x = _noise(seed, sensor.sensor_id, actor.actor_id, "x") * sensor.position_noise_stddev_m
    noise_y = _noise(seed, sensor.sensor_id, actor.actor_id, "y") * sensor.position_noise_stddev_m
    noise_z = _noise(seed, sensor.sensor_id, actor.actor_id, "z") * sensor.position_noise_stddev_m
    confidence = 0.98 - 0.25 * (distance / sensor.max_range_m)
    if sensor.sensor_type == "camera":
        confidence -= min(0.35, environment.precipitation_mm_per_h / 200)
        if environment.ambient_light_lux < 10:
            confidence -= 0.25
    elif sensor.sensor_type == "lidar" and environment.weather.value in {"fog", "rain", "snow"}:
        confidence -= 0.2
    return SensorDetection(
        actor_id=actor.actor_id,
        actor_type=actor.actor_type,
        relative_position_m=Vector3(
            x=round(distance * math.cos(math.radians(azimuth)) + noise_x, 6),
            y=round(distance * math.sin(math.radians(azimuth)) + noise_y, 6),
            z=round(relative_z + noise_z, 6),
        ),
        range_m=round(distance, 6),
        azimuth_deg=round(azimuth, 6),
        confidence=round(max(0, min(1, confidence)), 6),
    )


def _noise(seed: int, sensor_id: str, actor_id: str, axis: str) -> float:
    digest = sha256(f"{seed}:{sensor_id}:{actor_id}:{axis}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / (2**64 - 1) * 2 - 1


def _normalize_angle(value: float) -> float:
    return (value + 180) % 360 - 180
