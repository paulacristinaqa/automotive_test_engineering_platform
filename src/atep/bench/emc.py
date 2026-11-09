"""Transient pulses and functional status classification (Volume XI-5).

This is a conceptual model of how an EMC/transient test plan is written and
judged, not an EMC measurement. Pulse levels follow the shape of ISO 7637-2
and the ISO 16750-2 load dump with illustrative values; the ACU's reaction comes
from its input-protection model, not from circuit physics.

Functional status classes (paraphrasing ISO 16750-1):

- A: every function works as designed during and after the exposure.
- B: every function works during the exposure but may leave its tolerance;
  all return to normal by themselves.
- C: a function stops during the exposure and returns to normal by itself.
- D: a function stops and needs a simple driver action (an ignition cycle).
- E: a function does not return to normal without repair or replacement.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING

from atep.bench.airbag import ACU_STATUS_ID, AcuState

if TYPE_CHECKING:
    from atep.bench.airbag_bench import HilBench


class FunctionalStatus(IntEnum):
    """Lower is better, so `achieved <= required` means the requirement is met."""

    A = 1
    B = 2
    C = 3
    D = 4
    E = 5


FSC_MEANING = {
    FunctionalStatus.A: "works as designed during and after exposure",
    FunctionalStatus.B: "works during exposure, may leave tolerance, recovers by itself",
    FunctionalStatus.C: "stops during exposure, recovers by itself",
    FunctionalStatus.D: "stops during exposure, needs an ignition cycle",
    FunctionalStatus.E: "does not recover without repair",
}


class Coupling(StrEnum):
    SUPPLY = "supply"
    CAN = "can"


@dataclass(frozen=True)
class TransientPulse:
    name: str
    standard: str
    description: str
    peak_v: float
    width_us: int
    period_us: int
    count: int
    coupling: Coupling

    def __post_init__(self) -> None:
        if self.width_us <= 0 or self.count < 1:
            raise ValueError("a pulse needs a positive width and at least one repetition")
        if self.count > 1 and self.period_us <= self.width_us:
            raise ValueError("the repetition period must be longer than the pulse")

    def starts(self, at_us: int) -> list[int]:
        return [at_us + index * self.period_us for index in range(self.count)]

    @property
    def duration_us(self) -> int:
        return (self.count - 1) * self.period_us + self.width_us


PULSES = {
    pulse.name: pulse
    for pulse in (
        TransientPulse(
            "1",
            "ISO 7637-2 pulse 1",
            "Disconnection of an inductive load in parallel",
            -100.0,
            2_000,
            500_000,
            10,
            Coupling.SUPPLY,
        ),
        TransientPulse(
            "2a",
            "ISO 7637-2 pulse 2a",
            "Sudden interruption of current in a series load",
            50.0,
            50,
            500_000,
            10,
            Coupling.SUPPLY,
        ),
        TransientPulse(
            "3a",
            "ISO 7637-2 pulse 3a (coupled to CAN)",
            "Fast negative switching bursts",
            -150.0,
            10_000,
            100_000,
            10,
            Coupling.CAN,
        ),
        TransientPulse(
            "3b",
            "ISO 7637-2 pulse 3b (coupled to CAN)",
            "Fast positive switching bursts",
            100.0,
            10_000,
            100_000,
            10,
            Coupling.CAN,
        ),
        TransientPulse(
            "5b",
            "ISO 16750-2 load dump, suppressed",
            "Alternator load dump limited by central suppression to 35 V (Us 87 V)",
            35.0,
            400_000,
            60_000_000,
            1,
            Coupling.SUPPLY,
        ),
    )
}


@dataclass
class FscObservation:
    """What the evaluator saw around one exposure."""

    resets: int = 0
    readiness_lost: bool = False
    max_status_gap_us: int = 0
    frames_lost: int = 0
    error_frames: int = 0
    new_dtcs: list[int] = field(default_factory=list)
    recovered_automatically: bool = True
    recovered_after_ignition_cycle: bool = True
    unintended_deployment: bool = False
    status_period_us: int = 100_000
    probe: object = None

    @property
    def out_of_tolerance(self) -> bool:
        return (
            self.max_status_gap_us > self.status_period_us * 3 // 2
            or self.frames_lost > 0
            or bool(self.new_dtcs)
        )

    def classify(self) -> FunctionalStatus:
        if self.unintended_deployment:
            return FunctionalStatus.E  # fired squibs cannot be restored
        if not self.recovered_automatically:
            return FunctionalStatus.D if self.recovered_after_ignition_cycle else FunctionalStatus.E
        if self.resets or self.readiness_lost:
            return FunctionalStatus.C
        if self.out_of_tolerance:
            return FunctionalStatus.B
        return FunctionalStatus.A


def _readiness_lost(history: list[tuple[int, bool]], start_us: int, end_us: int) -> bool:
    ready = False
    for at_us, value in history:
        if at_us > end_us:
            break
        if at_us <= start_us:
            ready = value
        elif not value:
            return True
    return not ready


def _max_gap(times: list[int], start_us: int, end_us: int) -> int:
    window = [t for t in times if start_us <= t <= end_us]
    edges = [start_us, *window, end_us]
    return max(b - a for a, b in zip(edges, edges[1:], strict=False))


def observe(
    bench: "HilBench",
    *,
    exposure_us: int,
    recovery_us: int = 7_000_000,
    probe_after_us: int | None = None,
    probe: Callable[[], object] | None = None,
) -> FscObservation:
    """Watch the ACU through an exposure already started on `bench`, then judge recovery.

    Call right after starting the exposure. If the ACU has not recovered by itself after
    `recovery_us`, the evaluator cycles the ignition through the relay card and checks again.
    An optional `probe` runs `probe_after_us` into the exposure to record what the ACU does
    while it is exposed.
    """
    acu = bench.acu
    start = bench.now_us
    cycles = acu.power_cycles
    lost = len(bench.link.lost)
    dtcs_before = set(acu.dtcs)
    probed: object = None
    if probe is not None and probe_after_us is not None and probe_after_us < exposure_us:
        bench.wait(probe_after_us)
        probed = probe()
        bench.wait(start + exposure_us - bench.now_us)
    else:
        bench.wait(exposure_us)
    end = bench.now_us
    bench.wait(recovery_us)
    status_times = [frame.timestamp_us for frame in bench.frames(ACU_STATUS_ID)]
    observation = FscObservation(
        resets=acu.power_cycles - cycles,
        readiness_lost=_readiness_lost(acu.readiness_history, start, end),
        max_status_gap_us=_max_gap(status_times, start, end),
        frames_lost=len(bench.link.lost) - lost,
        error_frames=sum(
            1 for frame in bench.link.error_frames() if start <= frame.timestamp_us <= end
        ),
        new_dtcs=sorted(set(acu.dtcs) - dtcs_before),
        status_period_us=acu.cal.status_period_us,
        probe=probed,
    )
    observation.recovered_automatically = acu.state is AcuState.NORMAL and acu.ready
    if not observation.recovered_automatically:
        bench.scpi("REL", "ROUT:OPEN (@1)")
        bench.wait(1_000_000)
        bench.scpi("REL", "ROUT:CLOS (@1)")
        bench.wait(acu.cal.self_test_us + 200_000)
        observation.recovered_after_ignition_cycle = acu.state is AcuState.NORMAL and acu.ready
    observation.unintended_deployment = acu.crash is not None
    return observation
