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


class WorldActor(BaseModel):
    actor_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    actor_type: ActorType
    position_m: Vector3
    velocity_mps: Vector3 = Field(default_factory=lambda: Vector3(x=0, y=0, z=0))
    heading_deg: float = Field(default=0, ge=-180, le=180)
    length_m: float = Field(gt=0, le=100)
    width_m: float = Field(gt=0, le=20)
    height_m: float = Field(gt=0, le=20)


class WorldSceneCreate(BaseModel):
    scene_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    coordinate_frame: CoordinateFrame
    roads: list[Road] = Field(min_length=1, max_length=100)
    actors: list[WorldActor] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def unique_identifiers_and_single_ego(self) -> "WorldSceneCreate":
        road_ids = [road.road_id for road in self.roads]
        lane_ids = [lane.lane_id for road in self.roads for lane in road.lanes]
        actor_ids = [actor.actor_id for actor in self.actors]
        if len(set(road_ids)) != len(road_ids) or len(set(lane_ids)) != len(lane_ids):
            raise ValueError("road and lane identifiers must be unique")
        if len(set(actor_ids)) != len(actor_ids):
            raise ValueError("actor identifiers must be unique")
        if sum(actor.actor_type == ActorType.EGO_VEHICLE for actor in self.actors) != 1:
            raise ValueError("a scene must contain exactly one ego_vehicle")
        return self


class WorldSceneAdvance(BaseModel):
    duration_ms: int = Field(ge=1, le=3_600_000)
    expected_revision: int = Field(ge=1)


class WorldSceneResponse(BaseModel):
    id: UUID
    vehicle_id: str
    scene_id: str
    name: str
    coordinate_frame: CoordinateFrame
    roads: list[Road]
    actors: list[WorldActor]
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
