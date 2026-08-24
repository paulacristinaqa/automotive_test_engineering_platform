"""Canonical Android Automotive/VHAL mappings exposed to Vehicle Gateway clients."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class VhalAccess(StrEnum):
    READ = "read"
    READ_WRITE = "read_write"


class VhalAreaType(StrEnum):
    GLOBAL = "global"
    SEAT = "seat"
    WHEEL = "wheel"


class VhalValueType(StrEnum):
    BOOLEAN = "boolean"
    FLOAT = "float"
    INT32 = "int32"


class VhalConversion(StrEnum):
    IDENTITY = "identity"
    METRES_PER_SECOND_TO_KILOMETRES_PER_HOUR = "mps_to_kph"


class VhalPropertyMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    android_property: str
    canonical_property: str
    value_type: VhalValueType
    access: VhalAccess
    area_type: VhalAreaType
    area_id_required: bool
    vhal_unit: str | None = None
    atep_unit: str | None = None
    conversion: VhalConversion = VhalConversion.IDENTITY


class VhalMappingCatalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: str
    mappings: tuple[VhalPropertyMapping, ...]


VHAL_MAPPING_CATALOG = VhalMappingCatalog(
    contract_version="atep.vehicle-gateway.vhal-mappings.v1",
    mappings=(
        VhalPropertyMapping(
            android_property="PERF_VEHICLE_SPEED",
            canonical_property="vehicle_speed",
            value_type=VhalValueType.FLOAT,
            access=VhalAccess.READ,
            area_type=VhalAreaType.GLOBAL,
            area_id_required=False,
            vhal_unit="m/s",
            atep_unit="km/h",
            conversion=VhalConversion.METRES_PER_SECOND_TO_KILOMETRES_PER_HOUR,
        ),
        VhalPropertyMapping(
            android_property="GEAR_SELECTION",
            canonical_property="gear",
            value_type=VhalValueType.INT32,
            access=VhalAccess.READ,
            area_type=VhalAreaType.GLOBAL,
            area_id_required=False,
        ),
        VhalPropertyMapping(
            android_property="IGNITION_STATE",
            canonical_property="ignition_state",
            value_type=VhalValueType.INT32,
            access=VhalAccess.READ,
            area_type=VhalAreaType.GLOBAL,
            area_id_required=False,
        ),
        VhalPropertyMapping(
            android_property="EV_BATTERY_LEVEL",
            canonical_property="battery_energy",
            value_type=VhalValueType.FLOAT,
            access=VhalAccess.READ,
            area_type=VhalAreaType.GLOBAL,
            area_id_required=False,
            vhal_unit="Wh",
            atep_unit="Wh",
        ),
        VhalPropertyMapping(
            android_property="INFO_EV_BATTERY_CAPACITY",
            canonical_property="battery_capacity",
            value_type=VhalValueType.FLOAT,
            access=VhalAccess.READ,
            area_type=VhalAreaType.GLOBAL,
            area_id_required=False,
            vhal_unit="Wh",
            atep_unit="Wh",
        ),
        VhalPropertyMapping(
            android_property="EV_CHARGE_PORT_CONNECTED",
            canonical_property="charging_port_connected",
            value_type=VhalValueType.BOOLEAN,
            access=VhalAccess.READ,
            area_type=VhalAreaType.GLOBAL,
            area_id_required=False,
        ),
        VhalPropertyMapping(
            android_property="FUEL_LEVEL",
            canonical_property="fuel_level",
            value_type=VhalValueType.FLOAT,
            access=VhalAccess.READ,
            area_type=VhalAreaType.GLOBAL,
            area_id_required=False,
            vhal_unit="mL",
            atep_unit="mL",
        ),
        VhalPropertyMapping(
            android_property="HVAC_TEMPERATURE_CURRENT",
            canonical_property="cabin_temperature",
            value_type=VhalValueType.FLOAT,
            access=VhalAccess.READ,
            area_type=VhalAreaType.SEAT,
            area_id_required=True,
            vhal_unit="celsius",
            atep_unit="celsius",
        ),
        VhalPropertyMapping(
            android_property="TIRE_PRESSURE",
            canonical_property="tire_pressure",
            value_type=VhalValueType.FLOAT,
            access=VhalAccess.READ,
            area_type=VhalAreaType.WHEEL,
            area_id_required=True,
            vhal_unit="kPa",
            atep_unit="kPa",
        ),
    ),
)


def vhal_mapping_catalog() -> VhalMappingCatalog:
    """Return the immutable mapping catalogue shared through the public API."""

    return VHAL_MAPPING_CATALOG
