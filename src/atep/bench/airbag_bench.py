"""A ready-made bench around the virtual ACU: VCU stand-in, UDS tester and a simulated bus."""

from dataclasses import dataclass, field

from atep.bench.airbag import (
    ACU_CRASH_ID,
    ACU_DIAG_REQUEST_ID,
    ACU_DIAG_RESPONSE_ID,
    ACU_STATUS_ID,
    CRASH_E2E,
    STATUS_E2E,
    AcuCalibration,
    AirbagControlUnit,
    VehicleStatusSender,
)
from atep.bench.e2e import E2EChecker, E2EStatus
from atep.bench.isotp import IsoTpConfig
from atep.bench.link import SimulatedLink
from atep.bench.uds import UdsClient, UdsOutcome, UdsResult
from atep.bench.vector_trace import TraceFrame


def parse_dtc_response(response: bytes) -> dict[int, int]:
    """Turn a `59 02` response into {3-byte DTC: status}."""
    if response[:2] != b"\x59\x02":
        raise ValueError("not a ReadDTCInformation 0x02 response")
    body = response[3:]
    return {
        int.from_bytes(body[index : index + 3], "big"): body[index + 3]
        for index in range(0, len(body) - 3, 4)
    }


@dataclass
class AcuBench:
    """ACU on a simulated bus with a vehicle-status sender and a diagnostic tester."""

    calibration: AcuCalibration | None = None
    speed_kmh: float = 50.0
    acu: AirbagControlUnit = field(init=False)
    vcu: VehicleStatusSender = field(init=False)
    tester: UdsClient = field(init=False)
    link: SimulatedLink = field(init=False)

    def __post_init__(self) -> None:
        self.acu = AirbagControlUnit(self.calibration)
        self.vcu = VehicleStatusSender(speed_kmh=self.speed_kmh)
        self.tester = UdsClient(IsoTpConfig(tx_id=ACU_DIAG_REQUEST_ID, rx_id=ACU_DIAG_RESPONSE_ID))
        self.link = SimulatedLink([self.acu, self.vcu, self.tester])

    @property
    def now_us(self) -> int:
        return self.link.now_us

    def wait(self, duration_us: int) -> None:
        self.link.advance_to(self.link.now_us + duration_us)

    def power_on(self, *, kl30_v: float = 12.5, settle_us: int = 6_100_000) -> None:
        """Switch KL30 and KL15 on and wait until the self-test is over."""
        self.acu.set_power(self.now_us, kl30_v=kl30_v, kl15=True)
        self.wait(settle_us)

    def ask(self, request_hex: str) -> UdsResult:
        request = bytes.fromhex(request_hex)
        self.link.submit(self.tester, self.tester.request(request, self.now_us))
        self.link.run_until(lambda: self.tester.idle)
        return self.tester.last

    def read_dtcs(self, mask: int = 0xFF) -> dict[int, int]:
        result = self.ask(f"1902{mask:02X}")
        if result.outcome is not UdsOutcome.POSITIVE:
            raise RuntimeError(f"DTC read failed: {result.outcome}")
        return parse_dtc_response(result.response)

    def frames(self, arbitration_id: int, *, since_us: int = 0) -> list[TraceFrame]:
        return [
            frame
            for frame in self.link.trace
            if frame.arbitration_id == arbitration_id and frame.timestamp_us >= since_us
        ]

    def status_frames(self, *, since_us: int = 0) -> list[TraceFrame]:
        return self.frames(ACU_STATUS_ID, since_us=since_us)

    def crash_frames(self, *, since_us: int = 0) -> list[TraceFrame]:
        return self.frames(ACU_CRASH_ID, since_us=since_us)

    def e2e_statuses(self, arbitration_id: int) -> list[E2EStatus]:
        config = STATUS_E2E if arbitration_id == ACU_STATUS_ID else CRASH_E2E
        checker = E2EChecker(config)
        return [checker.check(frame.data) for frame in self.frames(arbitration_id)]
