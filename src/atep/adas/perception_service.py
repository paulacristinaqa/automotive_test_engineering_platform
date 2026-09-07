from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import AdasPerceptionResult, AdasSensorObservation, AdasWorldScene
from atep.adas.schemas import (
    ActorType,
    PerceptionPrediction,
    PerceptionResultCreate,
    PerceptionResultResponse,
    PerceptionScore,
    PerceptionTargetType,
    TrafficControl,
    TrafficControlType,
    WorldActor,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AdasPerceptionConflictError,
    AdasSceneVersionConflictError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event

GroundTruthKey = tuple[PerceptionTargetType, str, str]


def perception_response(
    result: AdasPerceptionResult,
    observation: AdasSensorObservation,
    scene: AdasWorldScene,
) -> PerceptionResultResponse:
    return PerceptionResultResponse(
        id=result.id,
        result_id=result.result_id,
        observation_id=observation.observation_id,
        scene_id=scene.scene_id,
        scene_revision=result.scene_revision,
        model_name=result.model_name,
        model_version=result.model_version,
        predictions=result.predictions,
        overall_score=result.overall_score,
        scores_by_target=result.scores_by_target,
        requested_by_user_id=result.requested_by_user_id,
        created_at=result.created_at,
    )


async def require_perception_result(
    session: AsyncSession, *, observation_id: UUID, result_id: str
) -> AdasPerceptionResult:
    result = await session.scalar(
        select(AdasPerceptionResult).where(
            AdasPerceptionResult.sensor_observation_id == observation_id,
            AdasPerceptionResult.result_id == result_id,
        )
    )
    if result is None:
        raise ResourceNotFoundError("adas_perception_result")
    return result


async def create_perception_result(
    session: AsyncSession,
    *,
    scene: AdasWorldScene,
    observation: AdasSensorObservation,
    command: PerceptionResultCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> AdasPerceptionResult:
    if scene.revision != observation.scene_revision:
        raise AdasSceneVersionConflictError(
            expected=observation.scene_revision, actual=scene.revision
        )
    overall, by_target = score_predictions(
        predictions=command.predictions,
        ground_truth=build_ground_truth(scene=scene, observation=observation),
    )
    result = AdasPerceptionResult(
        sensor_observation_id=observation.id,
        result_id=command.result_id,
        scene_revision=observation.scene_revision,
        model_name=command.model_name,
        model_version=command.model_version,
        predictions=[item.model_dump(mode="json") for item in command.predictions],
        overall_score=overall.model_dump(mode="json"),
        scores_by_target={
            key.value: value.model_dump(mode="json") for key, value in by_target.items()
        },
        requested_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(result)
            await session.flush()
    except IntegrityError as exc:
        raise AdasPerceptionConflictError() from exc
    evidence = {
        "scene_id": scene.scene_id,
        "observation_id": observation.observation_id,
        "result_id": result.result_id,
        "scene_revision": result.scene_revision,
        "model_name": result.model_name,
        "model_version": result.model_version,
        "prediction_count": len(command.predictions),
        "overall_score": result.overall_score,
    }
    enqueue_event(
        session,
        event_type="atep.adas.perception.result.created.v1",
        aggregate_type="adas_perception_result",
        aggregate_id=result.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.perception_result_created",
        resource_type="adas_perception_result",
        resource_id=result.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return result


def build_ground_truth(
    *, scene: AdasWorldScene, observation: AdasSensorObservation
) -> set[GroundTruthKey]:
    visible_actor_ids = {str(item["actor_id"]) for item in observation.detections}
    truth: set[GroundTruthKey] = set()
    for raw_actor in scene.actors:
        actor = WorldActor.model_validate(raw_actor)
        if actor.actor_id not in visible_actor_ids:
            continue
        target_type = (
            PerceptionTargetType.PEDESTRIAN
            if actor.actor_type == ActorType.PEDESTRIAN
            else PerceptionTargetType.OBJECT
        )
        truth.add((target_type, actor.actor_id, actor.actor_type.value))
    for road in scene.roads:
        for lane in road["lanes"]:
            truth.add((PerceptionTargetType.LANE, str(lane["lane_id"]), "lane"))
    for raw_control in scene.traffic_controls:
        control = TrafficControl.model_validate(raw_control)
        if control.control_type == TrafficControlType.TRAFFIC_LIGHT:
            classification = control.light_state.value if control.light_state else "off"
            truth.add((PerceptionTargetType.SIGNAL, control.control_id, classification))
        else:
            truth.add((PerceptionTargetType.SIGN, control.control_id, control.control_type.value))
    return truth


def score_predictions(
    *, predictions: Iterable[PerceptionPrediction], ground_truth: set[GroundTruthKey]
) -> tuple[PerceptionScore, dict[PerceptionTargetType, PerceptionScore]]:
    prediction_list = list(predictions)
    matched: set[GroundTruthKey] = set()
    counts = {target: [0, 0, 0] for target in PerceptionTargetType}
    for prediction in prediction_list:
        key = (
            prediction.target_type,
            prediction.ground_truth_id,
            prediction.classification,
        )
        if key in ground_truth and key not in matched:
            matched.add(key)
            counts[prediction.target_type][0] += 1
        else:
            counts[prediction.target_type][1] += 1
    for target_type, _, _ in ground_truth - matched:
        counts[target_type][2] += 1
    by_target = {
        target: _score(true_positive=values[0], false_positive=values[1], false_negative=values[2])
        for target, values in counts.items()
    }
    return _score(
        true_positive=sum(item[0] for item in counts.values()),
        false_positive=sum(item[1] for item in counts.values()),
        false_negative=sum(item[2] for item in counts.values()),
    ), by_target


def _score(*, true_positive: int, false_positive: int, false_negative: int) -> PerceptionScore:
    predicted = true_positive + false_positive
    expected = true_positive + false_negative
    precision = true_positive / predicted if predicted else (1.0 if expected == 0 else 0.0)
    recall = true_positive / expected if expected else (1.0 if predicted == 0 else 0.0)
    denominator = precision + recall
    f1_score = 2 * precision * recall / denominator if denominator else 0.0
    return PerceptionScore(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1_score=round(f1_score, 6),
    )
