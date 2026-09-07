from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ActorType(StrEnum):
    EGO_VEHICLE = "ego_vehicle"
    VEHICLE = "vehicle"
    PEDESTRIAN = "pedestrian"
    CYCLIST = "cyclist"
    STATIC_OBSTACLE = "static_obstacle"


class WeatherType(StrEnum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAIN = "rain"
    FOG = "fog"
    SNOW = "snow"


class TrafficLightState(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    FLASHING = "flashing"
    OFF = "off"


class TrafficControlType(StrEnum):
    TRAFFIC_LIGHT = "traffic_light"
    STOP_SIGN = "stop_sign"
    YIELD_SIGN = "yield_sign"
    SPEED_LIMIT_SIGN = "speed_limit_sign"


class SensorType(StrEnum):
    CAMERA = "camera"
    RADAR = "radar"
    LIDAR = "lidar"


class PerceptionTargetType(StrEnum):
    OBJECT = "object"
    PEDESTRIAN = "pedestrian"
    LANE = "lane"
    SIGN = "sign"
    SIGNAL = "signal"


class ManeuverType(StrEnum):
    MAINTAIN_LANE = "maintain_lane"
    LANE_CENTERING = "lane_centering"
    BRAKE = "brake"
    EMERGENCY_BRAKE = "emergency_brake"
    STOP = "stop"


class AdasAlertType(StrEnum):
    FORWARD_COLLISION = "forward_collision"
    UNSAFE_FOLLOWING_DISTANCE = "unsafe_following_distance"
    LANE_DEPARTURE = "lane_departure"
    RED_SIGNAL = "red_signal"


class AlertSeverity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class AdasScenarioType(StrEnum):
    AEB_CAR_TO_CAR = "aeb_car_to_car"
    AEB_PEDESTRIAN = "aeb_pedestrian"
    LANE_SUPPORT = "lane_support"
    TRAFFIC_SIGNAL_COMPLIANCE = "traffic_signal_compliance"


class AdasFaultType(StrEnum):
    DROP_PREDICTION = "drop_prediction"
    MISCLASSIFY_PREDICTION = "misclassify_prediction"


class ScenarioStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class Vector3(BaseModel):
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)
    z: float = Field(default=0, ge=-10_000, le=10_000)


class CoordinateFrame(BaseModel):
    convention: str = Field(default="ENU", pattern="^ENU$")
    origin_latitude_deg: float = Field(ge=-90, le=90)
    origin_longitude_deg: float = Field(ge=-180, le=180)
    origin_altitude_m: float = Field(default=0, ge=-500, le=10_000)


class Lane(BaseModel):
    lane_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    centerline: list[Vector3] = Field(min_length=2, max_length=1_000)
    width_m: float = Field(default=3.5, gt=0, le=20)
    speed_limit_kph: float = Field(default=50, gt=0, le=400)


class Road(BaseModel):
    road_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    lanes: list[Lane] = Field(min_length=1, max_length=32)


class EnvironmentConditions(BaseModel):
    weather: WeatherType = WeatherType.CLEAR
    precipitation_mm_per_h: float = Field(default=0, ge=0, le=500)
    visibility_m: float = Field(default=10_000, ge=1, le=100_000)
    ambient_light_lux: float = Field(default=10_000, ge=0, le=150_000)
    road_friction_coefficient: float = Field(default=0.9, ge=0.05, le=1.5)
    temperature_c: float = Field(default=20, ge=-60, le=70)
    wind_speed_mps: float = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def weather_is_consistent(self) -> "EnvironmentConditions":
        if (
            self.weather in {WeatherType.RAIN, WeatherType.SNOW}
            and self.precipitation_mm_per_h == 0
        ):
            raise ValueError("rain and snow require positive precipitation")
        if self.weather == WeatherType.FOG and self.visibility_m > 2_000:
            raise ValueError("fog visibility cannot exceed 2000 metres")
        return self


class TrafficControl(BaseModel):
    control_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    control_type: TrafficControlType
    position_m: Vector3
    lane_ids: list[str] = Field(min_length=1, max_length=32)
    light_state: TrafficLightState | None = None
    speed_limit_kph: float | None = Field(default=None, gt=0, le=400)

    @model_validator(mode="after")
    def type_specific_value(self) -> "TrafficControl":
        if self.control_type == TrafficControlType.TRAFFIC_LIGHT and self.light_state is None:
            raise ValueError("traffic lights require light_state")
        if (
            self.control_type == TrafficControlType.SPEED_LIMIT_SIGN
            and self.speed_limit_kph is None
        ):
            raise ValueError("speed limit signs require speed_limit_kph")
        if self.control_type != TrafficControlType.TRAFFIC_LIGHT and self.light_state is not None:
            raise ValueError("light_state is only valid for traffic lights")
        return self


class TrajectoryWaypoint(BaseModel):
    time_offset_ms: int = Field(ge=0, le=86_400_000)
    position_m: Vector3
    velocity_mps: Vector3 | None = None


class WorldActor(BaseModel):
    actor_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    actor_type: ActorType
    position_m: Vector3
    velocity_mps: Vector3 = Field(default_factory=lambda: Vector3(x=0, y=0, z=0))
    heading_deg: float = Field(default=0, ge=-180, le=180)
    length_m: float = Field(gt=0, le=100)
    width_m: float = Field(gt=0, le=20)
    height_m: float = Field(gt=0, le=20)
    trajectory: list[TrajectoryWaypoint] = Field(default_factory=list, max_length=10_000)

    @model_validator(mode="after")
    def trajectory_time_is_strictly_increasing(self) -> "WorldActor":
        times = [waypoint.time_offset_ms for waypoint in self.trajectory]
        if times and times[0] != 0:
            raise ValueError("a trajectory must start at time offset zero")
        if any(current >= following for current, following in zip(times, times[1:], strict=False)):
            raise ValueError("trajectory waypoint times must be strictly increasing")
        return self


class WorldSceneCreate(BaseModel):
    scene_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    coordinate_frame: CoordinateFrame
    roads: list[Road] = Field(min_length=1, max_length=100)
    actors: list[WorldActor] = Field(min_length=1, max_length=1_000)
    environment: EnvironmentConditions = Field(default_factory=EnvironmentConditions)
    traffic_controls: list[TrafficControl] = Field(default_factory=list, max_length=1_000)

    @model_validator(mode="after")
    def unique_identifiers_and_single_ego(self) -> "WorldSceneCreate":
        road_ids = [road.road_id for road in self.roads]
        lane_ids = [lane.lane_id for road in self.roads for lane in road.lanes]
        actor_ids = [actor.actor_id for actor in self.actors]
        control_ids = [control.control_id for control in self.traffic_controls]
        if len(set(road_ids)) != len(road_ids) or len(set(lane_ids)) != len(lane_ids):
            raise ValueError("road and lane identifiers must be unique")
        if len(set(actor_ids)) != len(actor_ids):
            raise ValueError("actor identifiers must be unique")
        if len(set(control_ids)) != len(control_ids):
            raise ValueError("traffic control identifiers must be unique")
        known_lanes = set(lane_ids)
        if any(set(control.lane_ids) - known_lanes for control in self.traffic_controls):
            raise ValueError("traffic controls must reference lanes in the scene")
        if sum(actor.actor_type == ActorType.EGO_VEHICLE for actor in self.actors) != 1:
            raise ValueError("a scene must contain exactly one ego_vehicle")
        return self


class WorldSceneAdvance(BaseModel):
    duration_ms: int = Field(ge=1, le=3_600_000)
    expected_revision: int = Field(ge=1)


class WorldSceneContextUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    environment: EnvironmentConditions
    traffic_controls: list[TrafficControl] = Field(default_factory=list, max_length=1_000)


class WorldSceneResponse(BaseModel):
    id: UUID
    vehicle_id: str
    scene_id: str
    name: str
    coordinate_frame: CoordinateFrame
    roads: list[Road]
    actors: list[WorldActor]
    environment: EnvironmentConditions
    traffic_controls: list[TrafficControl]
    revision: int
    simulation_time_ms: int
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class WorldScenePage(BaseModel):
    items: list[WorldSceneResponse]
    total: int
    limit: int
    offset: int


class SensorConfigurationCreate(BaseModel):
    sensor_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    sensor_type: SensorType
    mount_position_m: Vector3 = Field(default_factory=lambda: Vector3(x=0, y=0, z=1.2))
    yaw_deg: float = Field(default=0, ge=-180, le=180)
    max_range_m: float = Field(gt=0, le=2_000)
    horizontal_fov_deg: float = Field(gt=0, le=360)
    latency_ms: int = Field(default=0, ge=0, le=10_000)
    position_noise_stddev_m: float = Field(default=0, ge=0, le=50)


class SensorConfigurationResponse(BaseModel):
    id: UUID
    scene_id: str
    sensor_id: str
    sensor_type: SensorType
    mount_position_m: Vector3
    yaw_deg: float
    max_range_m: float
    horizontal_fov_deg: float
    latency_ms: int
    position_noise_stddev_m: float
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class SensorConfigurationPage(BaseModel):
    items: list[SensorConfigurationResponse]
    total: int
    limit: int
    offset: int


class SensorObservationCreate(BaseModel):
    observation_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    expected_scene_revision: int = Field(ge=1)
    seed: int = Field(ge=0, le=2_147_483_647)


class SensorDetection(BaseModel):
    actor_id: str
    actor_type: ActorType
    relative_position_m: Vector3
    range_m: float = Field(ge=0)
    azimuth_deg: float = Field(ge=-180, le=180)
    confidence: float = Field(ge=0, le=1)


class SensorObservationResponse(BaseModel):
    id: UUID
    observation_id: str
    scene_id: str
    sensor_id: str
    sensor_type: SensorType
    scene_revision: int
    scene_simulation_time_ms: int
    observed_simulation_time_ms: int
    seed: int
    detections: list[SensorDetection]
    metrics: dict[str, int | float]
    requested_by_user_id: UUID
    created_at: datetime


class PerceptionPrediction(BaseModel):
    prediction_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    target_type: PerceptionTargetType
    ground_truth_id: str = Field(min_length=1, max_length=64)
    classification: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)


class PerceptionResultCreate(BaseModel):
    result_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    model_name: str = Field(min_length=1, max_length=120)
    model_version: str = Field(min_length=1, max_length=64)
    predictions: list[PerceptionPrediction] = Field(default_factory=list, max_length=10_000)

    @model_validator(mode="after")
    def prediction_identifiers_are_unique(self) -> "PerceptionResultCreate":
        identifiers = [item.prediction_id for item in self.predictions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("prediction identifiers must be unique")
        return self


class PerceptionScore(BaseModel):
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1_score: float = Field(ge=0, le=1)


class PerceptionResultResponse(BaseModel):
    id: UUID
    result_id: str
    observation_id: str
    scene_id: str
    scene_revision: int
    model_name: str
    model_version: str
    predictions: list[PerceptionPrediction]
    overall_score: PerceptionScore
    scores_by_target: dict[PerceptionTargetType, PerceptionScore]
    requested_by_user_id: UUID
    created_at: datetime


class PlanningEvaluationCreate(BaseModel):
    evaluation_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    expected_scene_revision: int = Field(ge=1)
    ego_lane_id: str = Field(min_length=1, max_length=64)
    minimum_following_distance_m: float = Field(default=15, gt=0, le=200)
    collision_warning_ttc_s: float = Field(default=4, ge=0.5, le=20)
    emergency_brake_ttc_s: float = Field(default=1.5, ge=0.1, le=10)
    lane_departure_margin_m: float = Field(default=0.2, ge=0, le=2)

    @model_validator(mode="after")
    def ttc_thresholds_are_ordered(self) -> "PlanningEvaluationCreate":
        if self.emergency_brake_ttc_s >= self.collision_warning_ttc_s:
            raise ValueError("emergency brake TTC must be lower than collision warning TTC")
        return self


class PlanningRiskMetrics(BaseModel):
    nearest_lead_distance_m: float | None = Field(default=None, ge=0)
    minimum_ttc_s: float | None = Field(default=None, ge=0)
    lane_center_offset_m: float = Field(ge=0)
    safe_following_distance: bool
    lane_departure: bool
    red_signal_detected: bool


class AdasAlert(BaseModel):
    alert_type: AdasAlertType
    severity: AlertSeverity
    message: str = Field(min_length=1, max_length=240)


class PlanningEvaluationResponse(BaseModel):
    id: UUID
    evaluation_id: str
    perception_result_id: str
    scene_id: str
    scene_revision: int
    maneuver: ManeuverType
    risk_metrics: PlanningRiskMetrics
    alerts: list[AdasAlert]
    requested_by_user_id: UUID
    created_at: datetime


class AdasFaultInjection(BaseModel):
    fault_type: AdasFaultType
    prediction_id: str = Field(min_length=1, max_length=64)
    replacement_classification: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def replacement_matches_fault(self) -> "AdasFaultInjection":
        if (
            self.fault_type == AdasFaultType.MISCLASSIFY_PREDICTION
            and self.replacement_classification is None
        ):
            raise ValueError("misclassification requires replacement_classification")
        if (
            self.fault_type == AdasFaultType.DROP_PREDICTION
            and self.replacement_classification is not None
        ):
            raise ValueError("drop prediction does not accept replacement_classification")
        return self


class AdasScenarioExecute(BaseModel):
    execution_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    scenario_type: AdasScenarioType
    expected_scene_revision: int = Field(ge=1)
    ego_lane_id: str = Field(min_length=1, max_length=64)
    expected_maneuver: ManeuverType
    required_alerts: list[AdasAlertType] = Field(default_factory=list, max_length=4)
    minimum_overall_f1: float = Field(default=0, ge=0, le=1)
    minimum_following_distance_m: float = Field(default=15, gt=0, le=200)
    collision_warning_ttc_s: float = Field(default=4, ge=0.5, le=20)
    emergency_brake_ttc_s: float = Field(default=1.5, ge=0.1, le=10)
    lane_departure_margin_m: float = Field(default=0.2, ge=0, le=2)
    fault_injections: list[AdasFaultInjection] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def scenario_invariants(self) -> "AdasScenarioExecute":
        if self.emergency_brake_ttc_s >= self.collision_warning_ttc_s:
            raise ValueError("emergency brake TTC must be lower than collision warning TTC")
        if len(self.required_alerts) != len(set(self.required_alerts)):
            raise ValueError("required alerts must be unique")
        prediction_ids = [item.prediction_id for item in self.fault_injections]
        if len(prediction_ids) != len(set(prediction_ids)):
            raise ValueError("a prediction can receive at most one fault injection")
        return self


class AdasScenarioAssertion(BaseModel):
    name: str
    passed: bool
    expected: str
    observed: str


class AdasScenarioCoverage(BaseModel):
    scenario_type: AdasScenarioType
    target_types: list[PerceptionTargetType]
    alert_types: list[AdasAlertType]
    maneuver: ManeuverType
    fault_types: list[AdasFaultType]
    assertions_passed: int = Field(ge=0)
    assertions_total: int = Field(ge=1)
    assertion_coverage: float = Field(ge=0, le=1)


class AdasScenarioResponse(BaseModel):
    id: UUID
    execution_id: str
    scene_id: str
    perception_result_id: str
    scenario_type: AdasScenarioType
    scene_revision: int
    status: ScenarioStatus
    duplicate: bool = False
    maneuver: ManeuverType
    alerts: list[AdasAlert]
    assertions: list[AdasScenarioAssertion]
    fault_injections: list[AdasFaultInjection]
    coverage: AdasScenarioCoverage
    regression_fingerprint: str
    requested_by_user_id: UUID
    created_at: datetime


class AdasScenarioPage(BaseModel):
    items: list[AdasScenarioResponse]
    total: int
    limit: int
    offset: int
