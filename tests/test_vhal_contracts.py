from atep.vehicles.schemas import PROPERTY_NAME_PATTERN
from atep.vehicles.vhal_contracts import (
    VhalAreaType,
    VhalConversion,
    vhal_mapping_catalog,
)


def test_vhal_catalog_is_versioned_unique_and_uses_canonical_properties() -> None:
    catalog = vhal_mapping_catalog()

    assert catalog.contract_version == "atep.vehicle-gateway.vhal-mappings.v1"
    android_properties = [mapping.android_property for mapping in catalog.mappings]
    assert len(android_properties) == len(set(android_properties))
    assert all(
        PROPERTY_NAME_PATTERN.fullmatch(mapping.canonical_property) for mapping in catalog.mappings
    )


def test_vhal_catalog_makes_units_conversions_and_areas_explicit() -> None:
    mappings = {mapping.android_property: mapping for mapping in vhal_mapping_catalog().mappings}

    speed = mappings["PERF_VEHICLE_SPEED"]
    assert speed.vhal_unit == "m/s"
    assert speed.atep_unit == "km/h"
    assert speed.conversion is VhalConversion.METRES_PER_SECOND_TO_KILOMETRES_PER_HOUR
    assert speed.area_type is VhalAreaType.GLOBAL
    assert speed.area_id_required is False

    cabin_temperature = mappings["HVAC_TEMPERATURE_CURRENT"]
    assert cabin_temperature.area_type is VhalAreaType.SEAT
    assert cabin_temperature.area_id_required is True

    tire_pressure = mappings["TIRE_PRESSURE"]
    assert tire_pressure.area_type is VhalAreaType.WHEEL
    assert tire_pressure.area_id_required is True
