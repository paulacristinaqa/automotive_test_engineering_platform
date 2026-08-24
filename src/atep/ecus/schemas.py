import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

ECU_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
FAULT_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,31}$")
COMMAND_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$")
TASK_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
BEHAVIOR_STATE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


class EcuType(StrEnum):
    MOTOR = "motor"
    BATTERY = "battery"
    DOOR = "door"
    ABS = "abs"
    ADAS = "adas"
    CLIMATE = "climate"
    GATEWAY = "gateway"
    LIGHTING = "lighting"
    BODY = "body"


class EcuOperationalState(StrEnum):
    OFFLINE = "offline"
    BOOTING = "booting"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAULT = "fault"
    SHUTDOWN = "shutdown"


class EcuFaultSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EcuFaultStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class EcuMemoryCell(BaseModel):
    address: int = Field(ge=0, le=65_535)
    value: int = Field(ge=0, le=255)


class EcuCyclicTask(BaseModel):
    task_id: str = Field(min_length=3, max_length=40)
    period_ms: int = Field(ge=1, le=60_000)
    offset_ms: int = Field(default=0, ge=0, le=59_999)

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not TASK_ID_PATTERN.fullmatch(normalized):
            raise ValueError("task IDs must use lowercase letters, numbers, and underscores")
        return normalized

    @model_validator(mode="after")
    def keep_offset_within_period(self) -> "EcuCyclicTask":
        if self.offset_ms >= self.period_ms:
            raise ValueError("task offset must be smaller than its period")
        return self


class EcuFault(BaseModel):
    code: str = Field(min_length=3, max_length=32)
    severity: EcuFaultSeverity
    status: EcuFaultStatus = EcuFaultStatus.PENDING
    description: str = Field(default="", max_length=200)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not FAULT_CODE_PATTERN.fullmatch(normalized):
            raise ValueError("fault codes must use uppercase letters, numbers, and underscores")
        return normalized

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()


class EcuStatePayload(BaseModel):
    operational_state: EcuOperationalState = EcuOperationalState.OFFLINE
    memory: list[EcuMemoryCell] = Field(default_factory=list, max_length=256)
    faults: list[EcuFault] = Field(default_factory=list, max_length=64)
    cyclic_tasks: list[EcuCyclicTask] = Field(default_factory=list, max_length=32)
    behavior_state: dict[str, int | bool | str] = Field(default_factory=dict, max_length=32)

    @field_validator("behavior_state")
    @classmethod
    def bound_behavior_state(
        cls, value: dict[str, int | bool | str]
    ) -> dict[str, int | bool | str]:
        for key, item in value.items():
            if not BEHAVIOR_STATE_KEY_PATTERN.fullmatch(key):
                raise ValueError("behavior-state keys must use lowercase canonical names")
            integer_is_unsafe = (
                isinstance(item, int)
                and not isinstance(item, bool)
                and abs(item) > 9_007_199_254_740_991
            )
            if integer_is_unsafe:
                raise ValueError("behavior-state integers must remain JSON-safe")
            if isinstance(item, str) and len(item) > 120:
                raise ValueError("behavior-state strings must not exceed 120 characters")
        return value

    @model_validator(mode="after")
    def require_unique_entries_and_consistent_fault_state(self) -> "EcuStatePayload":
        addresses = [cell.address for cell in self.memory]
        if len(addresses) != len(set(addresses)):
            raise ValueError("ECU memory addresses must be unique")
        codes = [fault.code for fault in self.faults]
        if len(codes) != len(set(codes)):
            raise ValueError("ECU fault codes must be unique")
        task_ids = [task.task_id for task in self.cyclic_tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("ECU cyclic task IDs must be unique")
        has_critical_fault = any(
            fault.severity is EcuFaultSeverity.CRITICAL
            and fault.status is EcuFaultStatus.CONFIRMED
            for fault in self.faults
        )
        if has_critical_fault and self.operational_state is not EcuOperationalState.FAULT:
            raise ValueError("a confirmed critical fault requires the ECU fault state")
        return self


class EcuCreate(EcuStatePayload):
    identifier: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=120)
    ecu_type: EcuType

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not ECU_IDENTIFIER_PATTERN.fullmatch(normalized):
            raise ValueError("ECU identifiers must use lowercase letters, numbers, and hyphens")
        return normalized

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()


class EcuStateReplace(EcuStatePayload):
    expected_version: int = Field(ge=1)


class EcuResponse(EcuStatePayload):
    id: UUID
    vehicle_id: str
    identifier: str
    display_name: str
    ecu_type: EcuType
    version: int
    simulation_time_ms: int
    boot_count: int
    profile_version: str
    created_at: datetime
    updated_at: datetime


class EcuPage(BaseModel):
    items: list[EcuResponse]
    total: int
    limit: int
    offset: int


class EcuResetMode(StrEnum):
    SOFT = "soft"
    HARD = "hard"
    POWER_CYCLE = "power_cycle"


class EcuAdvanceCommand(BaseModel):
    command_id: str = Field(min_length=8, max_length=64)
    expected_version: int = Field(ge=1)
    duration_ms: int = Field(ge=1, le=600_000)

    @field_validator("command_id")
    @classmethod
    def validate_command_id(cls, value: str) -> str:
        normalized = value.strip()
        if not COMMAND_ID_PATTERN.fullmatch(normalized):
            raise ValueError("command IDs must be URL-safe and contain 8 to 64 characters")
        return normalized


class EcuResetCommand(BaseModel):
    command_id: str = Field(min_length=8, max_length=64)
    expected_version: int = Field(ge=1)
    mode: EcuResetMode

    @field_validator("command_id")
    @classmethod
    def validate_command_id(cls, value: str) -> str:
        return EcuAdvanceCommand.validate_command_id(value)


class EcuTaskRunSummary(BaseModel):
    task_id: str
    execution_count: int
    first_due_ms: int | None
    last_due_ms: int | None


class EcuProfileTaskResponse(EcuCyclicTask):
    state_effect: str


class EcuBehaviorProfileResponse(BaseModel):
    ecu_type: EcuType
    profile_version: str
    description: str
    tasks: list[EcuProfileTaskResponse]
    initial_state: dict[str, int | bool | str]


class EcuAdvanceResponse(BaseModel):
    command_id: str
    vehicle_id: str
    ecu_id: str
    duration_ms: int
    previous_version: int
    state_version: int
    previous_time_ms: int
    simulation_time_ms: int
    task_runs: list[EcuTaskRunSummary]
    profile_version: str
    behavior_state: dict[str, int | bool | str]
    duplicate: bool = False
    created_at: datetime


class EcuResetResponse(BaseModel):
    command_id: str
    vehicle_id: str
    ecu_id: str
    mode: EcuResetMode
    reset_duration_ms: int
    previous_version: int
    state_version: int
    previous_time_ms: int
    simulation_time_ms: int
    boot_count: int
    memory_preserved: bool
    faults_preserved: bool
    duplicate: bool = False
    created_at: datetime
