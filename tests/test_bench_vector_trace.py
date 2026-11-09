import io
from datetime import UTC, datetime, timedelta, timezone

import can
import pytest

from atep.bench.vector_trace import TraceFrame, anchor_from, render_asc, render_blf

START = datetime(2026, 11, 9, 10, 0, 0, 123_456, tzinfo=UTC)
FRAMES = [
    TraceFrame(3_000_001, 0x123, False, bytes(range(16)), is_fd=True, bitrate_switch=True),
    TraceFrame(1_000, 0x180, False, bytes([1, 2, 3, 4])),
    TraceFrame(2_500, 0x18FEF100, True, bytes(range(8))),
    TraceFrame(4_000, 0x7FF, False, b""),
    TraceFrame(5_000, 0x456, False, bytes(12), is_fd=True),
]


def _key(message: can.Message) -> tuple[int, bool, bool, bool, bytes]:
    return (
        message.arbitration_id,
        message.is_extended_id,
        message.is_fd,
        message.bitrate_switch,
        bytes(message.data),
    )


def _expected() -> list[tuple[int, int, bool, bool, bool, bytes]]:
    ordered = sorted(FRAMES, key=lambda item: item.timestamp_us)
    return [
        (f.timestamp_us, f.arbitration_id, f.is_extended_id, f.is_fd, f.bitrate_switch, f.data)
        for f in ordered
    ]


def test_asc_round_trips_through_python_can_reader_with_exact_microseconds() -> None:
    text = render_asc(FRAMES, measurement_start=START)
    messages = list(can.ASCReader(io.StringIO(text)))
    actual = [(round(m.timestamp * 1_000_000), *_key(m)) for m in messages]
    assert actual == _expected()


def test_asc_header_uses_utc_measurement_start_without_locale() -> None:
    text = render_asc([], measurement_start=START)
    assert text.splitlines()[:5] == [
        "date Mon Nov 09 10:00:00.123 2026",
        "base hex  timestamps absolute",
        "internal events logged",
        "Begin Triggerblock Mon Nov 09 10:00:00.123 2026",
        "   0.000000 Start of measurement",
    ]
    assert text.endswith("End TriggerBlock\n")


def test_asc_is_independent_of_time_zone_representation() -> None:
    brazil = START.astimezone(timezone(timedelta(hours=-3)))
    assert render_asc(FRAMES, measurement_start=brazil) == render_asc(
        FRAMES, measurement_start=START
    )
    naive = START.replace(tzinfo=None)
    assert render_asc(FRAMES, measurement_start=naive) == render_asc(
        FRAMES, measurement_start=START
    )


def test_blf_round_trips_within_one_microsecond_and_starts_at_measurement_start() -> None:
    content = render_blf(FRAMES, measurement_start=START)
    reader = can.BLFReader(io.BytesIO(content))
    assert reader.start_timestamp == pytest.approx(anchor_from(START).timestamp(), abs=1e-3)
    messages = list(reader)
    expected = _expected()
    assert [_key(m) for m in messages] == [item[1:] for item in expected]
    for message, item in zip(messages, expected, strict=True):
        offset_us = (message.timestamp - anchor_from(START).timestamp()) * 1_000_000
        assert offset_us == pytest.approx(item[0], abs=1)


def test_blf_output_is_reproducible() -> None:
    assert render_blf(FRAMES, measurement_start=START) == render_blf(
        FRAMES, measurement_start=START
    )


def test_anchor_truncates_to_milliseconds() -> None:
    assert anchor_from(START).microsecond == 123_000


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timestamp_us": -1}, "negative"),
        ({"channel": 0}, "channels"),
        ({"bitrate_switch": True}, "bitrate switch"),
        ({"data": bytes(9)}, "longer"),
    ],
)
def test_trace_frame_rejects_invalid_frames(kwargs: dict[str, object], message: str) -> None:
    base: dict[str, object] = {
        "timestamp_us": 0,
        "arbitration_id": 0x100,
        "is_extended_id": False,
        "data": b"",
    }
    with pytest.raises(ValueError, match=message):
        TraceFrame(**(base | kwargs))  # type: ignore[arg-type]
