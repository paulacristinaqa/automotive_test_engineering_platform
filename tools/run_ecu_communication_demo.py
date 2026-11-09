"""ECU communication demo (Volume XI-2).

Part 1 runs a UDS diagnostic session between a tester and the virtual ECU over
ISO-TP. Part 2 sends an E2E-protected cyclic message with injected faults to a
receiver and a timeout monitor. Every step has an expected result; the demo
writes Vector traces and a JSON report and fails on any deviation.

    python tools/run_ecu_communication_demo.py --output out/ecu-communication
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from atep.bench.bus import BenchBusConfig, BenchInterface, open_bench_bus
from atep.bench.cyclic import CyclicFault, CyclicSender, E2EReceiver
from atep.bench.e2e import E2EConfig, E2EStatus
from atep.bench.isotp import IsoTpConfig
from atep.bench.link import BusNodeRunner, SimulatedLink
from atep.bench.supervision import SupervisedMessage, SupervisionState, TimeoutMonitor
from atep.bench.uds import Nrc, UdsClient, UdsOutcome, UdsResult, physical_addressing
from atep.bench.vector_trace import TraceFrame, render_asc, render_blf
from atep.bench.virtual_ecu import EcuDiagnosticProfile, VirtualEcu, expected_key

MEASUREMENT_START = datetime(2026, 1, 1, tzinfo=UTC)
REPAIR_SHOP_CODE = bytes(range(0x30, 0x58))  # 40 bytes: forces a multi-frame request


@dataclass(frozen=True)
class DiagnosticStep:
    name: str
    build: Callable[[list[UdsResult]], bytes]
    outcome: UdsOutcome
    nrc: int | None = None
    response_prefix: bytes = b""
    min_pending: int = 0
    wait_before_us: int = 0


def _fixed(hex_request: str) -> Callable[[list[UdsResult]], bytes]:
    request = bytes.fromhex(hex_request)
    return lambda _: request


def _key_from_last(results: list[UdsResult]) -> bytes:
    return b"\x27\x02" + expected_key(results[-1].response[2:])


def _wrong_key(results: list[UdsResult]) -> bytes:
    key = bytearray(expected_key(results[-1].response[2:]))
    key[-1] ^= 0x01
    return b"\x27\x02" + bytes(key)


WRITE = b"\x2e\xf1\x98" + REPAIR_SHOP_CODE

DIAGNOSTIC_STEPS = (
    DiagnosticStep(
        "Enter extended session",
        _fixed("1003"),
        UdsOutcome.POSITIVE,
        response_prefix=bytes.fromhex("5003"),
    ),
    DiagnosticStep(
        "Read VIN (multi-frame response)",
        _fixed("22F190"),
        UdsOutcome.POSITIVE,
        response_prefix=b"\x62\xf1\x90WATEP",
    ),
    DiagnosticStep(
        "Write without security access",
        lambda _: WRITE,
        UdsOutcome.NEGATIVE,
        nrc=Nrc.SECURITY_ACCESS_DENIED,
    ),
    DiagnosticStep(
        "Request seed", _fixed("2701"), UdsOutcome.POSITIVE, response_prefix=bytes.fromhex("6701")
    ),
    DiagnosticStep("Send a wrong key", _wrong_key, UdsOutcome.NEGATIVE, nrc=Nrc.INVALID_KEY),
    DiagnosticStep(
        "Request a new seed",
        _fixed("2701"),
        UdsOutcome.POSITIVE,
        response_prefix=bytes.fromhex("6701"),
    ),
    DiagnosticStep(
        "Send the key", _key_from_last, UdsOutcome.POSITIVE, response_prefix=bytes.fromhex("6702")
    ),
    DiagnosticStep(
        "Write repair shop code (multi-frame request)",
        lambda _: WRITE,
        UdsOutcome.POSITIVE,
        response_prefix=bytes.fromhex("6EF198"),
    ),
    DiagnosticStep(
        "Read back the repair shop code",
        _fixed("22F198"),
        UdsOutcome.POSITIVE,
        response_prefix=b"\x62\xf1\x98" + REPAIR_SHOP_CODE,
    ),
    DiagnosticStep(
        "Slow DID answers with response pending",
        _fixed("22F195"),
        UdsOutcome.POSITIVE,
        response_prefix=b"\x62\xf1\x95",
        min_pending=1,
    ),
    DiagnosticStep(
        "Tester present with suppressed response", _fixed("3E80"), UdsOutcome.NO_RESPONSE_EXPECTED
    ),
    DiagnosticStep(
        "Read confirmed DTCs",
        _fixed("1902FF"),
        UdsOutcome.POSITIVE,
        response_prefix=bytes.fromhex("5902FF9A0113"),
    ),
    DiagnosticStep(
        "Clear all DTCs", _fixed("14FFFFFF"), UdsOutcome.POSITIVE, response_prefix=b"\x54"
    ),
    DiagnosticStep(
        "DTC list is empty after clear",
        _fixed("1902FF"),
        UdsOutcome.POSITIVE,
        response_prefix=bytes.fromhex("5902FF"),
    ),
    DiagnosticStep(
        "Unsupported service",
        _fixed("3101FF00"),
        UdsOutcome.NEGATIVE,
        nrc=Nrc.SERVICE_NOT_SUPPORTED,
    ),
    DiagnosticStep(
        "Security access after S3 timeout",
        _fixed("2701"),
        UdsOutcome.NEGATIVE,
        nrc=Nrc.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
        wait_before_us=6_000_000,
    ),
    DiagnosticStep(
        "Enter extended session again",
        _fixed("1003"),
        UdsOutcome.POSITIVE,
        response_prefix=bytes.fromhex("5003"),
    ),
    DiagnosticStep(
        "Hard reset", _fixed("1101"), UdsOutcome.POSITIVE, response_prefix=bytes.fromhex("5101")
    ),
    DiagnosticStep(
        "Write after reset falls back to default session",
        lambda _: WRITE,
        UdsOutcome.NEGATIVE,
        nrc=Nrc.SERVICE_NOT_SUPPORTED_IN_ACTIVE_SESSION,
    ),
)

E2E_CONFIG = E2EConfig(data_id=0x0123, length=8)
E2E_FAULTS = {
    3: CyclicFault.CORRUPT_CRC,
    5: CyclicFault.REPEAT_COUNTER,
    8: CyclicFault.DROP,
    11: CyclicFault.SKIP_COUNTERS,
} | {cycle: CyclicFault.DROP for cycle in range(20, 26)}
EXPECTED_E2E = [
    E2EStatus.INITIAL,
    E2EStatus.OK,
    E2EStatus.OK,
    E2EStatus.WRONG_CRC,
    E2EStatus.OK_SOME_LOST,
    E2EStatus.REPEATED,
    E2EStatus.OK,
    E2EStatus.OK,
    E2EStatus.OK_SOME_LOST,
    E2EStatus.OK,
    E2EStatus.WRONG_SEQUENCE,
]
EXPECTED_SUPERVISION = [
    SupervisionState.OK,
    SupervisionState.TIMEOUT,
    SupervisionState.OK,
    SupervisionState.TIMEOUT,
]


@dataclass
class StepReport:
    name: str
    request: str
    expected: str
    outcome: str
    response: str
    nrc: int | None
    pending_count: int
    response_time_us: int
    passed: bool


@dataclass
class DemoReport:
    mode: str
    steps: list[StepReport] = field(default_factory=list)
    e2e_statuses: list[str] = field(default_factory=list)
    supervision_events: list[dict[str, object]] = field(default_factory=list)
    e2e_passed: bool = False
    supervision_passed: bool = False
    files: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return (
            bool(self.steps)
            and all(step.passed for step in self.steps)
            and (self.mode == "bus" or (self.e2e_passed and self.supervision_passed))
        )


def ecu_transport() -> IsoTpConfig:
    """The ECU asks for blocks of 4 frames, 2 ms apart, to exercise flow control."""
    return IsoTpConfig(tx_id=0x7E8, rx_id=0x7E0, block_size=4, st_min_us=2_000)


def ecu_profile() -> EcuDiagnosticProfile:
    return EcuDiagnosticProfile(slow_dids={0xF195: 120_000})


def _judge(step: DiagnosticStep, result: UdsResult) -> StepReport:
    passed = (
        result.outcome is step.outcome
        and (step.nrc is None or result.nrc == step.nrc)
        and result.response.startswith(step.response_prefix)
        and result.pending_count >= step.min_pending
    )
    expected = step.outcome.value + (f" NRC 0x{step.nrc:02X}" if step.nrc is not None else "")
    return StepReport(
        name=step.name,
        request=result.request.hex(" ").upper(),
        expected=expected,
        outcome=result.outcome.value,
        response=result.response.hex(" ").upper(),
        nrc=result.nrc,
        pending_count=result.pending_count,
        response_time_us=result.response_time_us,
        passed=passed,
    )


def run_diagnostics_simulated() -> tuple[list[StepReport], list[TraceFrame]]:
    tester = UdsClient(physical_addressing())
    ecu = VirtualEcu(ecu_transport(), ecu_profile())
    link = SimulatedLink([tester, ecu])
    reports: list[StepReport] = []
    for step in DIAGNOSTIC_STEPS:
        if step.wait_before_us:
            link.advance_to(link.now_us + step.wait_before_us)
        link.submit(tester, tester.request(step.build(tester.results), link.now_us))
        link.run_until(lambda: tester.idle)
        reports.append(_judge(step, tester.last))
        link.advance_to(link.now_us + 10_000)
    return reports, link.trace


def run_diagnostics_on_bus(config: BenchBusConfig) -> list[StepReport]:
    """Same steps on a python-can bus with the wall clock. S3 waits are skipped."""
    tester = UdsClient(physical_addressing())
    ecu = VirtualEcu(ecu_transport(), ecu_profile())
    tester_bus, ecu_bus = open_bench_bus(config), open_bench_bus(config)
    reports: list[StepReport] = []
    try:
        tester_runner = BusNodeRunner(tester_bus, tester)
        ecu_runner = BusNodeRunner(ecu_bus, ecu)
        for step in DIAGNOSTIC_STEPS:
            if step.wait_before_us:
                continue
            tester_runner.send(tester.request(step.build(tester.results), tester_runner.now_us()))
            while not tester.idle:
                ecu_runner.step(timeout_s=0.0005)
                tester_runner.step(timeout_s=0.0005)
            reports.append(_judge(step, tester.last))
    finally:
        tester_bus.shutdown()
        ecu_bus.shutdown()
    return reports


def run_e2e_simulated() -> tuple[E2EReceiver, TimeoutMonitor, list[TraceFrame]]:
    sender = CyclicSender(0x101, 20_000, E2E_CONFIG, stop_after_us=700_000, faults=E2E_FAULTS)
    receiver = E2EReceiver(0x101, E2E_CONFIG)
    monitor = TimeoutMonitor([SupervisedMessage("vcu_torque", 0x101, 20_000, 100_000)])
    link = SimulatedLink([sender, receiver, monitor])
    link.advance_to(1_000_000)
    return receiver, monitor, link.trace


def _write(path: Path, content: bytes, report: DemoReport) -> None:
    path.write_bytes(content)
    report.files[path.name] = hashlib.sha256(content).hexdigest()


def run_demo(output: Path, *, bus: BenchBusConfig | None = None) -> DemoReport:
    output.mkdir(parents=True, exist_ok=True)
    if bus is not None:
        report = DemoReport(mode="bus", steps=run_diagnostics_on_bus(bus))
    else:
        report = DemoReport(mode="simulated")
        steps, diagnostic_trace = run_diagnostics_simulated()
        report.steps = steps
        receiver, monitor, e2e_trace = run_e2e_simulated()
        statuses = receiver.statuses()
        report.e2e_statuses = [status.value for status in statuses]
        report.e2e_passed = statuses[: len(EXPECTED_E2E)] == EXPECTED_E2E
        report.supervision_events = [
            {"message": event.name, "state": event.state.value, "at_us": event.at_us}
            for event in monitor.events
        ]
        report.supervision_passed = [e.state for e in monitor.events] == EXPECTED_SUPERVISION
        for name, trace in (("diagnostics", diagnostic_trace), ("e2e", e2e_trace)):
            _write(
                output / f"{name}.asc",
                render_asc(trace, measurement_start=MEASUREMENT_START).encode("utf-8"),
                report,
            )
            _write(
                output / f"{name}.blf",
                render_blf(trace, measurement_start=MEASUREMENT_START),
                report,
            )
    summary = json.loads(json.dumps(report, default=lambda item: item.__dict__))
    summary["passed"] = report.passed
    (output / "report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ATEP Volume XI-2 ECU communication demo")
    parser.add_argument("--output", type=Path, default=Path("out/ecu-communication"))
    parser.add_argument(
        "--bus",
        choices=[item.value for item in BenchInterface],
        help="run the diagnostic session on a python-can bus instead of the simulated link",
    )
    parser.add_argument("--channel", default="atep-diagnostics")
    args = parser.parse_args(argv)
    bus = (
        BenchBusConfig(interface=BenchInterface(args.bus), channel=args.channel)
        if args.bus
        else None
    )
    report = run_demo(args.output, bus=bus)
    for step in report.steps:
        mark = "PASS" if step.passed else "FAIL"
        print(f"[{mark}] {step.name}: {step.outcome} ({step.response_time_us} us)")
    if report.mode == "simulated":
        print(f"[{'PASS' if report.e2e_passed else 'FAIL'}] E2E statuses")
        print(f"[{'PASS' if report.supervision_passed else 'FAIL'}] Timeout supervision")
    print(f"{'PASSED' if report.passed else 'FAILED'}; files in {args.output}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
