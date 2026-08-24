from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from atep.ecus.schemas import EcuCyclicTask, EcuTaskRunSummary, EcuType


@dataclass(frozen=True)
class EcuBehaviorProfile:
    ecu_type: EcuType
    profile_version: str
    description: str
    tasks: tuple[EcuCyclicTask, ...]
    initial_state: Mapping[str, int | bool | str]
    state_effects: Mapping[str, str]


def _profile(
    ecu_type: EcuType,
    description: str,
    tasks: tuple[tuple[str, int, int, str], ...],
    initial_state: dict[str, int | bool | str],
) -> EcuBehaviorProfile:
    return EcuBehaviorProfile(
        ecu_type=ecu_type,
        profile_version="1.0.0",
        description=description,
        tasks=tuple(
            EcuCyclicTask(task_id=task_id, period_ms=period_ms, offset_ms=offset_ms)
            for task_id, period_ms, offset_ms, _ in tasks
        ),
        initial_state=MappingProxyType(initial_state),
        state_effects=MappingProxyType({task_id: effect for task_id, _, _, effect in tasks}),
    )


_PROFILES = {
    EcuType.MOTOR: _profile(
        EcuType.MOTOR,
        "Electric motor torque and thermal control baseline.",
        (
            ("torque_control", 10, 0, "increments torque_control_cycles"),
            ("motor_thermal", 100, 20, "increments thermal_samples"),
        ),
        {"torque_control_cycles": 0, "thermal_samples": 0, "inverter_enabled": False},
    ),
    EcuType.BATTERY: _profile(
        EcuType.BATTERY,
        "Battery cell monitoring and state-estimation baseline.",
        (
            ("cell_monitor", 100, 0, "increments cell_samples"),
            ("soc_estimation", 1000, 100, "increments soc_estimation_cycles"),
        ),
        {"cell_samples": 0, "soc_estimation_cycles": 0, "contactors_closed": False},
    ),
    EcuType.BODY: _profile(
        EcuType.BODY,
        "Body actuator and occupant-state coordination baseline.",
        (
            ("body_control", 50, 0, "increments body_control_cycles"),
            ("occupant_monitor", 250, 25, "increments occupant_samples"),
        ),
        {"body_control_cycles": 0, "occupant_samples": 0, "cabin_awake": False},
    ),
    EcuType.GATEWAY: _profile(
        EcuType.GATEWAY,
        "Protocol-independent routing and network-health baseline.",
        (
            ("route_scheduler", 5, 0, "increments routing_cycles"),
            ("network_health", 100, 10, "increments network_health_samples"),
        ),
        {"routing_cycles": 0, "network_health_samples": 0, "routing_enabled": False},
    ),
    EcuType.ABS: _profile(
        EcuType.ABS,
        "Safety-controller wheel regulation and supervision baseline.",
        (
            ("wheel_control", 10, 0, "increments wheel_control_cycles"),
            ("safety_monitor", 100, 5, "increments safety_checks"),
        ),
        {"wheel_control_cycles": 0, "safety_checks": 0, "intervention_active": False},
    ),
}


def behavior_profile(ecu_type: EcuType | str) -> EcuBehaviorProfile:
    normalized = EcuType(ecu_type)
    if normalized in _PROFILES:
        return _PROFILES[normalized]
    # Less specialized controllers use the body coordination baseline until a dedicated
    # profile is introduced. Their identity remains explicit in the returned contract.
    baseline = _PROFILES[EcuType.BODY]
    return EcuBehaviorProfile(
        ecu_type=normalized,
        profile_version=baseline.profile_version,
        description=f"{normalized.value} controller coordination baseline.",
        tasks=baseline.tasks,
        initial_state=baseline.initial_state,
        state_effects=baseline.state_effects,
    )


def behavior_profiles() -> tuple[EcuBehaviorProfile, ...]:
    return tuple(behavior_profile(ecu_type) for ecu_type in EcuType)


def execute_profile_transitions(
    profile: EcuBehaviorProfile,
    state: Mapping[str, int | bool | str],
    task_runs: list[EcuTaskRunSummary],
) -> dict[str, int | bool | str]:
    updated = dict(state)
    for run in task_runs:
        effect = profile.state_effects.get(run.task_id)
        if effect is None or run.execution_count == 0:
            continue
        state_key = effect.removeprefix("increments ")
        current = updated.get(state_key, 0)
        if not isinstance(current, int) or isinstance(current, bool):
            raise ValueError(f"profile counter {state_key} must be an integer")
        updated[state_key] = current + run.execution_count
    return updated
