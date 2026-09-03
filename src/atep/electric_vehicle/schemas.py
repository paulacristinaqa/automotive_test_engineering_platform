from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BatteryChemistry(StrEnum):
    LFP = "lfp"
    NMC = "nmc"


class BatteryContactorState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class BatteryOperatingState(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    PROTECTION = "protection"


class BatteryCellState(BaseModel):
    index: int = Field(ge=1, le=192)
    voltage_v: float = Field(ge=2.0, le=5.0)
    temperature_c: float = Field(ge=-50.0, le=120.0)
    soc_pct: float = Field(ge=0.0, le=100.0)


class BatteryPackCreate(BaseModel):
    chemistry: BatteryChemistry = BatteryChemistry.LFP
    series_cell_count: int = Field(default=96, ge=4, le=192)
    nominal_capacity_ah: float = Field(default=100.0, gt=0.0, le=1000.0)
    nominal_cell_voltage_v: float = Field(default=3.2, ge=2.5, le=4.3)
    internal_resistance_ohm: float = Field(default=0.08, gt=0.0, le=2.0)
    initial_soc_pct: float = Field(default=80.0, ge=0.0, le=100.0)
    initial_soh_pct: float = Field(default=100.0, ge=1.0, le=100.0)
    initial_temperature_c: float = Field(default=25.0, ge=-40.0, le=80.0)


class BatterySimulationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    duration_ms: int = Field(ge=1, le=3_600_000)
    pack_current_a: float = Field(ge=-1000.0, le=1000.0)
    ambient_temperature_c: float = Field(default=25.0, ge=-50.0, le=80.0)
    expected_version: int = Field(ge=1)


class BatteryPackResponse(BaseModel):
    vehicle_id: str
    chemistry: BatteryChemistry
    series_cell_count: int
    nominal_capacity_ah: float
    nominal_energy_kwh: float
    soc_pct: float
    soh_pct: float
    pack_voltage_v: float
    pack_current_a: float
    pack_power_kw: float
    pack_temperature_c: float
    minimum_cell_voltage_v: float
    maximum_cell_voltage_v: float
    minimum_cell_temperature_c: float
    maximum_cell_temperature_c: float
    contactor_state: BatteryContactorState
    operating_state: BatteryOperatingState
    cells: list[BatteryCellState]
    version: int
    simulation_time_ms: int
    duplicate: bool = False

    @model_validator(mode="after")
    def validate_cell_count(self) -> "BatteryPackResponse":
        if len(self.cells) != self.series_cell_count:
            raise ValueError("cells must match series_cell_count")
        return self
