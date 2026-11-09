"""Virtual bench demo (Volume XI-1).

Sends the reference powertrain traffic on a python-can bus, receives it on a
second node, decodes every frame with cantools (an implementation independent of
ATEP) and writes the DBC, ASC and BLF files you can open in Vector CANoe or
CANalyzer.

    python tools/run_virtual_bench_demo.py --output out/virtual-bench
"""

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import cantools

from atep.bench.bus import (
    BenchBusConfig,
    BenchInterface,
    collect_frames,
    from_message,
    open_bench_bus,
    replay_frames,
)
from atep.bench.reference import build_schedule, reference_spec
from atep.bench.vector_dbc import encode_dbc, render_dbc
from atep.bench.vector_trace import render_asc, render_blf

DEFAULT_START = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class DemoReport:
    interface: str
    channel: str
    realtime: bool
    frames_scheduled: int
    frames_received: int = 0
    payload_mismatches: list[str] = field(default_factory=list)
    encode_mismatches: list[str] = field(default_factory=list)
    decode_mismatches: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return (
            self.frames_received == self.frames_scheduled
            and not self.payload_mismatches
            and not self.encode_mismatches
            and not self.decode_mismatches
        )


def _close(expected: Decimal, actual: float | int | str) -> bool:
    if isinstance(actual, str):
        return False
    return math.isclose(float(expected), float(actual), rel_tol=0, abs_tol=1e-6)


def _write(path: Path, content: bytes, report: DemoReport) -> None:
    path.write_bytes(content)
    report.files[path.name] = hashlib.sha256(content).hexdigest()


def run_demo(
    output: Path,
    *,
    config: BenchBusConfig,
    duration_ms: int = 1_000,
    realtime: bool = False,
    measurement_start: datetime = DEFAULT_START,
) -> DemoReport:
    spec = reference_spec()
    dbc_text = render_dbc(spec)
    database = cantools.database.load_string(dbc_text, database_format="dbc")
    if not isinstance(database, cantools.database.can.Database):
        raise TypeError("expected a CAN database")
    schedule = build_schedule(spec, duration_ms=duration_ms)
    report = DemoReport(
        interface=config.interface.value,
        channel=config.channel,
        realtime=realtime,
        frames_scheduled=len(schedule),
    )

    # Independent encoding check: cantools must produce the same payload as ATEP.
    for item in schedule:
        definition = database.get_message_by_frame_id(item.frame.arbitration_id)
        encoded = definition.encode({name: float(value) for name, value in item.values.items()})
        if bytes(encoded) != item.frame.data:
            report.encode_mismatches.append(f"{item.contract_id}@{item.frame.timestamp_us}us")

    transmitter = open_bench_bus(config)
    receiver = open_bench_bus(config)
    try:
        replay_frames(transmitter, (item.frame for item in schedule), realtime=realtime)
        received = collect_frames(receiver, count=len(schedule), timeout_s=2.0)
    finally:
        transmitter.shutdown()
        receiver.shutdown()
    report.frames_received = len(received)

    for item, message in zip(schedule, received, strict=False):
        frame = from_message(message)
        label = f"{item.contract_id}@{item.frame.timestamp_us}us"
        if (frame.arbitration_id, frame.data, frame.is_fd) != (
            item.frame.arbitration_id,
            item.frame.data,
            item.frame.is_fd,
        ):
            report.payload_mismatches.append(label)
            continue
        decoded = database.decode_message(frame.arbitration_id, frame.data, decode_choices=False)
        if not isinstance(decoded, dict):
            report.decode_mismatches.append(label)
            continue
        for name, expected in item.values.items():
            actual = decoded.get(name)
            if not isinstance(actual, (int, float, str)) or not _close(expected, actual):
                report.decode_mismatches.append(f"{label}:{name}")

    output.mkdir(parents=True, exist_ok=True)
    frames = [item.frame for item in schedule]
    _write(output / "network.dbc", encode_dbc(dbc_text), report)
    _write(
        output / "trace.asc",
        render_asc(frames, measurement_start=measurement_start).encode("utf-8"),
        report,
    )
    _write(output / "trace.blf", render_blf(frames, measurement_start=measurement_start), report)
    summary = asdict(report) | {"passed": report.passed}
    (output / "report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--output", type=Path, default=Path("out/virtual-bench"))
    parser.add_argument(
        "--interface", choices=[item.value for item in BenchInterface], default="virtual"
    )
    parser.add_argument("--channel", default="atep-bench")
    parser.add_argument("--duration-ms", type=int, default=1_000)
    parser.add_argument("--realtime", action="store_true", help="pace frames in real time")
    args = parser.parse_args(argv)
    config = BenchBusConfig(
        interface=BenchInterface(args.interface),
        channel=args.channel,
        fd=True,
        data_bitrate_kbps=2000,
    )
    report = run_demo(
        args.output, config=config, duration_ms=args.duration_ms, realtime=args.realtime
    )
    print(
        f"{report.frames_received}/{report.frames_scheduled} frames received; "
        f"{'PASSED' if report.passed else 'FAILED'}; files in {args.output}"
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
