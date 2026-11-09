"""Virtual airbag control unit (ACU), the device under test of the virtual bench.

The model covers what a system tester checks on an ACU bench: squib loop
monitoring, a two-sensor deployment decision, warning lamp and self-test,
energy reserve after supply loss, DTCs with debouncing, E2E-protected CAN
outputs, supervision of a received message and UDS diagnostics.

It is a teaching model on logical time. The deployment algorithm and every
threshold are illustrative; real ACU calibrations are confidential and far
more elaborate.
"""

import math
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum, StrEnum
from uuid import UUID

from atep.bench.e2e import E2EConfig, E2EProtector
from atep.bench.isotp import IsoTpConfig
from atep.bench.supervision import SupervisedMessage, SupervisionState, TimeoutMonitor
from atep.bench.vector_dbc import DbcNode, VectorNetworkSpec
from atep.bench.vector_trace import TraceFrame
from atep.bench.virtual_ecu import Dtc, EcuDiagnosticProfile, VirtualEcu
from atep.can_network.dbc_service import decode_message, encode_message
from atep.can_network.schemas import CanDbcMessage, CanFrameContract

STANDARD_GRAVITY = 9.80665

# DTC status bits (ISO 14229-1).
TEST_FAILED = 0x01
PENDING = 0x04
CONFIRMED = 0x08
TEST_FAILED_SINCE_LAST_CLEAR = 0x20

ACU_ID = UUID("00000000-0000-4000-8000-0000000000a1")
VCU_ID = UUID("00000000-0000-4000-8000-0000000000c1")
TESTER_ID = UUID("00000000-0000-4000-8000-0000000000d1")

VEHICLE_STATUS_ID = 0x0A0
ACU_STATUS_ID = 0x090
ACU_CRASH_ID = 0x050
ACU_DIAG_REQUEST_ID = 0x7E2
ACU_DIAG_RESPONSE_ID = 0x7EA


def dtc_code(text: str, failure_type: int = 0x00) -> int:
    """Encode a DTC like `B1001` plus a failure type byte as the 3-byte UDS value."""
    systems = {"P": 0, "C": 1, "B": 2, "U": 3}
    if len(text) != 5 or text[0] not in systems:
        raise ValueError("DTC text must look like P0300, C0035, B1001 or U0121")
    try:
        digits = [int(character, 16) for character in text[1:]]
    except ValueError as error:
        raise ValueError("DTC digits must be hexadecimal") from error
    if digits[0] > 3 or not 0 <= failure_type <= 0xFF:
        raise ValueError("DTC first digit must be 0-3 and failure type one byte")
    high = (systems[text[0]] << 6) | (digits[0] << 4) | digits[1]
    low = (digits[2] << 4) | digits[3]
    return (high << 16) | (low << 8) | failure_type


class FailureType(IntEnum):
    NO_SUB_TYPE = 0x00
    CIRCUIT_OPEN = 0x13
    VOLTAGE_BELOW_THRESHOLD = 0x16
    VOLTAGE_ABOVE_THRESHOLD = 0x17
    RESISTANCE_BELOW_THRESHOLD = 0x1A
    RESISTANCE_ABOVE_THRESHOLD = 0x1B


class Loop(StrEnum):
    DRIVER_AIRBAG = "driver_airbag"
    PASSENGER_AIRBAG = "passenger_airbag"
    DRIVER_PRETENSIONER = "driver_pretensioner"
    PASSENGER_PRETENSIONER = "passenger_pretensioner"


LOOP_DTC = {
    Loop.DRIVER_AIRBAG: "B1001",
    Loop.PASSENGER_AIRBAG: "B1002",
    Loop.DRIVER_PRETENSIONER: "B1003",
    Loop.PASSENGER_PRETENSIONER: "B1004",
}
LOOP_BIT = {
    Loop.DRIVER_AIRBAG: 0x01,
    Loop.PASSENGER_AIRBAG: 0x02,
    Loop.DRIVER_PRETENSIONER: 0x04,
    Loop.PASSENGER_PRETENSIONER: 0x08,
}
LOOP_DID = {
    Loop.DRIVER_AIRBAG: 0x4001,
    Loop.PASSENGER_AIRBAG: 0x4002,
    Loop.DRIVER_PRETENSIONER: 0x4003,
    Loop.PASSENGER_PRETENSIONER: 0x4004,
}
SUPPLY_DTC = "B1010"
CRASH_RECORDED_DTC = dtc_code("B1050")
LOST_VEHICLE_STATUS_DTC = dtc_code("U0121")

DID_SUPPLY_VOLTAGE = 0x4010
DID_CRASH_RECORD = 0x4020
DID_SYSTEM_STATE = 0x4030


class AcuState(IntEnum):
    OFF = 0
    SELF_TEST = 1
    NORMAL = 2
    FAULT = 3
    CRASH = 4


class CrashSeverity(IntEnum):
    NONE = 0
    BELTS = 1
    AIRBAGS = 2


@dataclass(frozen=True)
class AcuCalibration:
    """Illustrative thresholds. Units are in the field names."""

    loop_min_ohm: float = 1.5
    loop_max_ohm: float = 5.0
    loop_open_ohm: float = 20.0
    undervoltage_v: float = 9.0
    overvoltage_v: float = 16.0
    minimum_operating_v: float = 6.0
    self_test_us: int = 6_000_000
    arming_delay_us: int = 200_000
    energy_reserve_us: int = 150_000
    fault_debounce_us: int = 500_000
    window_us: int = 30_000
    belt_threshold_kmh: float = 6.0
    airbag_threshold_kmh: float = 14.0
    safing_threshold_g: float = 3.0
    crash_event_us: int = 100_000
    status_period_us: int = 100_000
    crash_repeat_us: int = 20_000
    crash_repeats: int = 5
    vehicle_status_period_us: int = 100_000
    vehicle_status_timeout_us: int = 500_000


@dataclass(frozen=True)
class CrashPulse:
    """Deceleration samples in g from the main (central) and the independent safing sensor."""

    start_us: int
    sample_period_us: int
    main_g: tuple[float, ...]
    safing_g: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.sample_period_us <= 0 or self.start_us < 0:
            raise ValueError("pulse timing must be positive")
        if len(self.main_g) != len(self.safing_g) or not self.main_g:
            raise ValueError("main and safing sensors need the same number of samples")

    def samples(self) -> list[tuple[int, float, float]]:
        return [
            (self.start_us + index * self.sample_period_us, main, safing)
            for index, (main, safing) in enumerate(zip(self.main_g, self.safing_g, strict=True))
        ]

    @property
    def delta_v_kmh(self) -> float:
        seconds = self.sample_period_us / 1_000_000
        return sum(self.main_g) * STANDARD_GRAVITY * seconds * 3.6


def half_sine_pulse(
    start_us: int,
    *,
    peak_g: float,
    duration_ms: int,
    safing_ratio: float = 1.0,
    sample_period_us: int = 500,
) -> CrashPulse:
    """A barrier-crash-like deceleration: half a sine wave seen by both sensors."""
    count = max(1, duration_ms * 1000 // sample_period_us)
    main = tuple(peak_g * math.sin(math.pi * (index + 0.5) / count) for index in range(count))
    return CrashPulse(start_us, sample_period_us, main, tuple(g * safing_ratio for g in main))


def hammer_blow(
    start_us: int, *, peak_g: float = 200.0, duration_ms: int = 4, safing_g: float = 1.0
) -> CrashPulse:
    """Misuse case: a sharp hit on the ACU housing that the safing sensor barely sees.

    The default blow carries about 18 km/h of delta-v on the main sensor, above the
    airbag threshold, so only the safing check prevents a deployment.
    """
    pulse = half_sine_pulse(start_us, peak_g=peak_g, duration_ms=duration_ms)
    return CrashPulse(
        start_us, pulse.sample_period_us, pulse.main_g, tuple(safing_g for _ in pulse.main_g)
    )


@dataclass
class CrashRecord:
    first_fire_us: int
    vehicle_speed_kmh: float
    delta_v_kmh: float = 0.0
    fired: dict[Loop, int] = field(default_factory=dict)
    failed: list[Loop] = field(default_factory=list)

    @property
    def severity(self) -> CrashSeverity:
        airbags = {Loop.DRIVER_AIRBAG, Loop.PASSENGER_AIRBAG}
        if airbags & (set(self.fired) | set(self.failed)):
            return CrashSeverity.AIRBAGS
        return CrashSeverity.BELTS

    def mask(self, loops: list[Loop] | dict[Loop, int]) -> int:
        return sum(LOOP_BIT[loop] for loop in loops)


def _signal(name: str, start: int, length: int, **extra: str) -> dict[str, object]:
    return {
        "identifier": name,
        "start_bit": start,
        "bit_length": length,
        "byte_order": "intel",
    } | extra


def airbag_network_spec() -> VectorNetworkSpec:
    """CAN database of the ACU bench, used both to encode frames and to export a DBC."""
    contracts = [
        ("vehicle-status", VEHICLE_STATUS_ID, VCU_ID, [ACU_ID]),
        ("acu-status", ACU_STATUS_ID, ACU_ID, [VCU_ID]),
        ("acu-crash", ACU_CRASH_ID, ACU_ID, [VCU_ID]),
        ("acu-diag-request", ACU_DIAG_REQUEST_ID, TESTER_ID, [ACU_ID]),
        ("acu-diag-response", ACU_DIAG_RESPONSE_ID, ACU_ID, [TESTER_ID]),
    ]
    frames = [
        CanFrameContract.model_validate(
            {
                "identifier": name,
                "frame_id": frame_id,
                "dlc": 8,
                "producer_node_id": str(producer),
                "consumer_node_ids": [str(item) for item in consumers],
            }
        )
        for name, frame_id, producer, consumers in contracts
    ]
    raw_messages: list[dict[str, object]] = [
        {
            "contract_id": "vehicle-status",
            "signals": [
                _signal("VehicleSpeed", 0, 16, factor="0.01", minimum="0", unit="km/h"),
            ],
        },
        {
            "contract_id": "acu-status",
            "signals": [
                _signal("E2E_CRC", 0, 8),
                _signal("E2E_Counter", 8, 4),
                _signal("SystemState", 12, 4),
                _signal("WarningLamp", 16, 1),
                _signal("PassengerAirbagEnabled", 17, 1),
                _signal("DriverBuckled", 18, 1),
                _signal("CrashStored", 19, 1),
                _signal("ActiveFaults", 24, 8),
            ],
        },
        {
            "contract_id": "acu-crash",
            "signals": [
                _signal("E2E_CRC", 0, 8),
                _signal("E2E_Counter", 8, 4),
                _signal("CrashSeverity", 16, 4),
                _signal("FiredLoops", 24, 8),
                _signal("FailedLoops", 32, 8),
                _signal("DeltaV", 40, 16, factor="0.1", unit="km/h"),
            ],
        },
    ]
    messages = [CanDbcMessage.model_validate(item) for item in raw_messages]
    return VectorNetworkSpec(
        network_identifier="acu-bench-can",
        display_name="Virtual airbag control unit bench",
        revision="XI-3",
        bitrate_kbps=500,
        can_fd_enabled=False,
        data_bitrate_kbps=None,
        nodes=[DbcNode(ACU_ID, "ACU"), DbcNode(VCU_ID, "VCU"), DbcNode(TESTER_ID, "Tester")],
        frames=frames,
        messages={message.contract_id: message for message in messages},
    )


SPEC = airbag_network_spec()
STATUS_E2E = E2EConfig(data_id=ACU_STATUS_ID, length=8)
CRASH_E2E = E2EConfig(data_id=ACU_CRASH_ID, length=8)


def _encode(contract_id: str, values: dict[str, Decimal]) -> bytes:
    payload, _, _ = encode_message(SPEC.messages[contract_id], dlc=8, values=values)
    return bytes(payload)


def decode(contract_id: str, payload: bytes) -> dict[str, Decimal]:
    _, physical = decode_message(SPEC.messages[contract_id], payload=list(payload))
    return physical


class AcuDiagnostics(VirtualEcu):
    """UDS server of the ACU: DTCs and DIDs come from the live ACU model."""

    def __init__(self, acu: "AirbagControlUnit", config: IsoTpConfig) -> None:
        super().__init__(config, EcuDiagnosticProfile(dtcs=[]))
        self.acu = acu

    def read_data(self, did: int) -> bytes | None:
        acu = self.acu
        for loop, loop_did in LOOP_DID.items():
            if did == loop_did:
                ohms = acu.resistance[loop]
                centi = 0xFFFF if not math.isfinite(ohms) else min(round(ohms * 100), 0xFFFF)
                return centi.to_bytes(2, "big")
        if did == DID_SUPPLY_VOLTAGE:
            return min(round(acu.kl30_v * 100), 0xFFFF).to_bytes(2, "big")
        if did == DID_SYSTEM_STATE:
            return bytes([acu.state, int(acu.lamp_on)])
        if did == DID_CRASH_RECORD:
            crash = acu.crash
            if crash is None:
                return bytes(7)
            return (
                bytes([1, crash.mask(crash.fired), crash.mask(crash.failed)])
                + min(round(crash.delta_v_kmh * 10), 0xFFFF).to_bytes(2, "big")
                + min(round(crash.vehicle_speed_kmh), 0xFFFF).to_bytes(2, "big")
            )
        return super().read_data(did)

    def dtc_records(self) -> list[Dtc]:
        return list(self.acu.dtcs.values())

    def clear_dtcs(self) -> None:
        self.acu.clear_dtcs()


class AirbagControlUnit:
    """The ACU as a bench node. Bench inputs are methods that take the current time."""

    def __init__(self, calibration: AcuCalibration | None = None) -> None:
        self.cal = calibration or AcuCalibration()
        self.transport = IsoTpConfig(tx_id=ACU_DIAG_RESPONSE_ID, rx_id=ACU_DIAG_REQUEST_ID)
        self.diag = AcuDiagnostics(self, self.transport)
        self.resistance: dict[Loop, float] = {loop: 2.2 for loop in Loop}
        self.kl30_v = 12.0
        self.kl15 = False
        self.driver_buckled = True
        self.passenger_occupied = False
        self.passenger_airbag_enabled = True
        self.vehicle_speed_kmh = 0.0
        self.now_us = 0
        self.powered_since: int | None = None
        self.reserve_until: int | None = None
        self.monitor: TimeoutMonitor | None = None
        self.dtcs: dict[int, Dtc] = {}
        self.crash: CrashRecord | None = None
        self.lamp_history: list[tuple[int, bool]] = [(0, False)]
        self.power_cycles = 0
        self._failing_since: dict[int, int] = {}
        self._samples: deque[tuple[int, float, float, int]] = deque()
        self._window: deque[tuple[int, float, float, int]] = deque()
        self._next_status_at: int | None = None
        self._next_crash_at: int | None = None
        self._crash_remaining = 0
        self._status_e2e = E2EProtector(STATUS_E2E)
        self._crash_e2e = E2EProtector(CRASH_E2E)

    # Derived state -----------------------------------------------------------

    def operational(self, at_us: int | None = None) -> bool:
        at = self.now_us if at_us is None else at_us
        if self.powered_since is None:
            return False
        return self.reserve_until is None or at < self.reserve_until

    @property
    def can_active(self) -> bool:
        """The CAN transceiver needs the supply; the energy reserve only feeds the firing path."""
        return self.operational() and self.reserve_until is None

    @property
    def in_self_test(self) -> bool:
        return (
            self.powered_since is not None
            and self.now_us < self.powered_since + self.cal.self_test_us
        )

    def active_faults(self) -> list[Dtc]:
        return [
            dtc for dtc in self.dtcs.values() if dtc.status & TEST_FAILED and dtc.status & CONFIRMED
        ]

    @property
    def state(self) -> AcuState:
        if not self.operational():
            return AcuState.OFF
        if self.in_self_test:
            return AcuState.SELF_TEST
        if self.crash is not None:
            return AcuState.CRASH
        if self.active_faults():
            return AcuState.FAULT
        return AcuState.NORMAL

    @property
    def lamp_on(self) -> bool:
        return self.state in {AcuState.SELF_TEST, AcuState.FAULT, AcuState.CRASH}

    def lamp_at(self, at_us: int) -> bool:
        value = False
        for time_us, on in self.lamp_history:
            if time_us > at_us:
                break
            value = on
        return value

    # Bench inputs ------------------------------------------------------------

    def set_power(
        self, now_us: int, *, kl30_v: float | None = None, kl15: bool | None = None
    ) -> None:
        self._advance(now_us)
        if kl30_v is not None:
            self.kl30_v = kl30_v
        if kl15 is not None:
            self.kl15 = kl15
        supplied = self.kl30_v >= self.cal.minimum_operating_v
        if not self.kl15:
            self._shutdown()
        elif self.powered_since is None:
            if supplied:
                self._power_on(now_us)
        elif not supplied and self.reserve_until is None:
            self.reserve_until = now_us + self.cal.energy_reserve_us
        elif supplied and self.reserve_until is not None:
            self.reserve_until = None
            self._next_status_at = now_us + self.cal.status_period_us
        self._evaluate(now_us)

    def set_loop_resistance(self, now_us: int, loop: Loop, ohms: float) -> None:
        if ohms < 0:
            raise ValueError("resistance cannot be negative")
        self._advance(now_us)
        self.resistance[loop] = ohms
        self._evaluate(now_us)

    def set_occupancy(
        self,
        now_us: int,
        *,
        driver_buckled: bool | None = None,
        passenger_occupied: bool | None = None,
        passenger_airbag_enabled: bool | None = None,
    ) -> None:
        self._advance(now_us)
        if driver_buckled is not None:
            self.driver_buckled = driver_buckled
        if passenger_occupied is not None:
            self.passenger_occupied = passenger_occupied
        if passenger_airbag_enabled is not None:
            self.passenger_airbag_enabled = passenger_airbag_enabled
        self._evaluate(now_us)

    def inject_crash(self, pulse: CrashPulse) -> None:
        if pulse.start_us < self.now_us:
            raise ValueError("a crash pulse cannot start in the past")
        merged = sorted(
            [*self._samples, *((t, m, s, pulse.sample_period_us) for t, m, s in pulse.samples())],
            key=lambda item: item[0],
        )
        self._samples = deque(merged)

    def clear_dtcs(self) -> None:
        """UDS 0x14: the crash record stays; conditions still present are detected again."""
        for code in list(self.dtcs):
            if code != CRASH_RECORDED_DTC:
                del self.dtcs[code]
                self._failing_since.pop(code, None)
        self._evaluate(self.now_us)

    # Power -------------------------------------------------------------------

    def _power_on(self, now_us: int) -> None:
        self.powered_since = now_us
        self.reserve_until = None
        self.power_cycles += 1
        self.diag = AcuDiagnostics(self, self.transport)
        self.monitor = TimeoutMonitor(
            [
                SupervisedMessage(
                    "vehicle_status",
                    VEHICLE_STATUS_ID,
                    self.cal.vehicle_status_period_us,
                    self.cal.vehicle_status_timeout_us,
                )
            ],
            start_us=now_us,
        )
        self._next_status_at = now_us + self.cal.status_period_us
        self._window.clear()

    def _shutdown(self) -> None:
        self.powered_since = None
        self.reserve_until = None
        self.monitor = None
        self._next_status_at = None
        self._next_crash_at = None
        self._crash_remaining = 0
        self._failing_since.clear()
        self._window.clear()

    # Deployment --------------------------------------------------------------

    def _fire(self, loop: Loop, at_us: int, delta_v: float) -> None:
        if self.crash is None:
            self.crash = CrashRecord(first_fire_us=at_us, vehicle_speed_kmh=self.vehicle_speed_kmh)
            self.dtcs[CRASH_RECORDED_DTC] = Dtc(
                CRASH_RECORDED_DTC, TEST_FAILED | PENDING | CONFIRMED | TEST_FAILED_SINCE_LAST_CLEAR
            )
            self._crash_remaining = self.cal.crash_repeats + 1
            self._next_crash_at = at_us
        crash = self.crash
        crash.delta_v_kmh = max(crash.delta_v_kmh, delta_v)
        if loop in crash.fired or loop in crash.failed:
            return
        ohms = self.resistance[loop]
        if self.cal.loop_min_ohm <= ohms <= self.cal.loop_max_ohm:
            crash.fired[loop] = at_us
            # A fired squib is an open circuit afterwards.
            self.resistance[loop] = math.inf
        else:
            crash.failed.append(loop)

    def _algorithm(self, at_us: int, main_g: float, safing_g: float, period_us: int) -> None:
        self._window.append((at_us, main_g, safing_g, period_us))
        while self._window and self._window[0][0] <= at_us - self.cal.window_us:
            self._window.popleft()
        assert self.powered_since is not None
        if at_us < self.powered_since + self.cal.arming_delay_us:
            return
        if self.crash is not None and at_us > self.crash.first_fire_us + self.cal.crash_event_us:
            return
        delta_v = sum(m * p for _, m, _, p in self._window) * STANDARD_GRAVITY / 1e6 * 3.6
        if max(s for _, _, s, _ in self._window) < self.cal.safing_threshold_g:
            return
        if delta_v >= self.cal.belt_threshold_kmh:
            if self.driver_buckled:
                self._fire(Loop.DRIVER_PRETENSIONER, at_us, delta_v)
            if self.passenger_occupied:
                self._fire(Loop.PASSENGER_PRETENSIONER, at_us, delta_v)
        if delta_v >= self.cal.airbag_threshold_kmh:
            self._fire(Loop.DRIVER_AIRBAG, at_us, delta_v)
            if self.passenger_occupied and self.passenger_airbag_enabled:
                self._fire(Loop.PASSENGER_AIRBAG, at_us, delta_v)

    # Time --------------------------------------------------------------------

    def _advance(self, now_us: int) -> None:
        while self._samples and self._samples[0][0] <= now_us:
            at_us, main_g, safing_g, period_us = self._samples.popleft()
            if self.reserve_until is not None and at_us >= self.reserve_until:
                self._shutdown()
            if self.operational(at_us):
                self._algorithm(at_us, main_g, safing_g, period_us)
        if self.reserve_until is not None and now_us >= self.reserve_until:
            self._shutdown()
        self.now_us = max(self.now_us, now_us)
        if self.monitor is not None:
            self.monitor.poll(self.now_us)
        self._record_lamp()

    def _failing_codes(self) -> set[int]:
        codes: set[int] = set()
        fired = set(self.crash.fired) if self.crash else set()
        for loop, ohms in self.resistance.items():
            if loop in fired:
                continue
            if ohms >= self.cal.loop_open_ohm:
                codes.add(dtc_code(LOOP_DTC[loop], FailureType.CIRCUIT_OPEN))
            elif ohms > self.cal.loop_max_ohm:
                codes.add(dtc_code(LOOP_DTC[loop], FailureType.RESISTANCE_ABOVE_THRESHOLD))
            elif ohms < self.cal.loop_min_ohm:
                codes.add(dtc_code(LOOP_DTC[loop], FailureType.RESISTANCE_BELOW_THRESHOLD))
        if self.reserve_until is None:
            if self.kl30_v < self.cal.undervoltage_v:
                codes.add(dtc_code(SUPPLY_DTC, FailureType.VOLTAGE_BELOW_THRESHOLD))
            elif self.kl30_v > self.cal.overvoltage_v:
                codes.add(dtc_code(SUPPLY_DTC, FailureType.VOLTAGE_ABOVE_THRESHOLD))
        if (
            self.monitor is not None
            and self.monitor.state("vehicle_status") is SupervisionState.TIMEOUT
        ):
            codes.add(LOST_VEHICLE_STATUS_DTC)
        return codes

    def _evaluate(self, now_us: int) -> None:
        if not self.operational(now_us):
            self._record_lamp()
            return
        failing = self._failing_codes()
        for code in failing:
            dtc = self.dtcs.get(code)
            if dtc is None:
                self.dtcs[code] = Dtc(code, TEST_FAILED | PENDING | TEST_FAILED_SINCE_LAST_CLEAR)
            else:
                dtc.status |= TEST_FAILED | TEST_FAILED_SINCE_LAST_CLEAR
            self._failing_since.setdefault(code, now_us)
        for code, dtc in self.dtcs.items():
            if code == CRASH_RECORDED_DTC:
                continue
            if code not in failing:
                dtc.status &= ~TEST_FAILED
                self._failing_since.pop(code, None)
            elif now_us - self._failing_since[code] >= self.cal.fault_debounce_us:
                dtc.status |= CONFIRMED
        self._record_lamp()

    def _record_lamp(self) -> None:
        lamp = self.lamp_on
        if self.lamp_history[-1][1] != lamp:
            self.lamp_history.append((self.now_us, lamp))

    # CAN ---------------------------------------------------------------------

    def _status_frame(self, at_us: int) -> TraceFrame:
        values = {
            "E2E_CRC": Decimal(0),
            "E2E_Counter": Decimal(0),
            "SystemState": Decimal(int(self.state)),
            "WarningLamp": Decimal(int(self.lamp_on)),
            "PassengerAirbagEnabled": Decimal(
                int(self.passenger_occupied and self.passenger_airbag_enabled)
            ),
            "DriverBuckled": Decimal(int(self.driver_buckled)),
            "CrashStored": Decimal(int(self.crash is not None)),
            "ActiveFaults": Decimal(min(len(self.active_faults()), 255)),
        }
        data = self._status_e2e.protect(_encode("acu-status", values))
        return TraceFrame(at_us, ACU_STATUS_ID, False, data)

    def _crash_frame(self, at_us: int) -> TraceFrame:
        crash = self.crash
        assert crash is not None
        values = {
            "E2E_CRC": Decimal(0),
            "E2E_Counter": Decimal(0),
            "CrashSeverity": Decimal(int(crash.severity)),
            "FiredLoops": Decimal(crash.mask(crash.fired)),
            "FailedLoops": Decimal(crash.mask(crash.failed)),
            "DeltaV": Decimal(min(round(crash.delta_v_kmh * 10), 0xFFFF)) / 10,
        }
        data = self._crash_e2e.protect(_encode("acu-crash", values))
        return TraceFrame(at_us, ACU_CRASH_ID, False, data)

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        self._advance(now_us)
        if not self.can_active:
            return []
        if self.monitor is not None:
            self.monitor.on_frame(frame, now_us)
        if frame.arbitration_id == VEHICLE_STATUS_ID and len(frame.data) == 8:
            self.vehicle_speed_kmh = float(decode("vehicle-status", frame.data)["VehicleSpeed"])
        self._evaluate(now_us)
        return self.diag.on_frame(frame, now_us) + self.poll(now_us)

    def poll(self, now_us: int) -> list[TraceFrame]:
        self._advance(now_us)
        self._evaluate(now_us)
        frames: list[TraceFrame] = []
        if self.can_active:
            frames += self.diag.poll(now_us)
        transmit = self.can_active
        while self._next_status_at is not None and self._next_status_at <= now_us:
            if transmit:
                frames.append(self._status_frame(self._next_status_at))
            self._next_status_at += self.cal.status_period_us
        while (
            self._crash_remaining
            and self._next_crash_at is not None
            and self._next_crash_at <= now_us
        ):
            if transmit:
                frames.append(self._crash_frame(self._next_crash_at))
            self._crash_remaining -= 1
            self._next_crash_at += self.cal.crash_repeat_us
        return frames

    def next_deadline_us(self) -> int | None:
        values: list[int] = []
        if self._samples:
            values.append(self._samples[0][0])
        if self.reserve_until is not None:
            values.append(self.reserve_until)
        if self.operational():
            assert self.powered_since is not None
            if self.in_self_test:
                values.append(self.powered_since + self.cal.self_test_us)
            values.extend(
                since + self.cal.fault_debounce_us
                for code, since in self._failing_since.items()
                if not self.dtcs[code].status & CONFIRMED
            )
            if self.monitor is not None:
                monitor_deadline = self.monitor.next_deadline_us()
                if monitor_deadline is not None:
                    values.append(monitor_deadline)
            if self._next_status_at is not None:
                values.append(self._next_status_at)
            if self._crash_remaining and self._next_crash_at is not None:
                values.append(self._next_crash_at)
            if self.can_active and (deadline := self.diag.next_deadline_us()) is not None:
                values.append(deadline)
        return min(values) if values else None


@dataclass
class VehicleStatusSender:
    """VCU stand-in: sends the vehicle speed every 100 ms while `active`."""

    period_us: int = 100_000
    speed_kmh: float = 0.0
    active: bool = True
    next_at: int = 0

    def set_active(self, now_us: int, active: bool) -> None:
        if active and not self.active:
            self.next_at = now_us
        self.active = active

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        frames: list[TraceFrame] = []
        while self.active and self.next_at <= now_us:
            speed = Decimal(f"{self.speed_kmh:.2f}")
            data = _encode("vehicle-status", {"VehicleSpeed": speed})
            frames.append(TraceFrame(self.next_at, VEHICLE_STATUS_ID, False, data))
            self.next_at += self.period_us
        return frames

    def next_deadline_us(self) -> int | None:
        return self.next_at if self.active else None
