"""Timeout supervision of cyclic CAN messages, on logical time."""

from dataclasses import dataclass, field
from enum import StrEnum

from atep.bench.vector_trace import TraceFrame


class SupervisionState(StrEnum):
    WAITING = "waiting"
    OK = "ok"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class SupervisedMessage:
    """A cyclic message is lost when no frame arrives within `timeout_us`."""

    name: str
    arbitration_id: int
    period_us: int
    timeout_us: int
    is_extended_id: bool = False
    recovery_frames: int = 1

    def __post_init__(self) -> None:
        if self.period_us <= 0 or self.timeout_us < self.period_us:
            raise ValueError("timeout must be at least one period")
        if self.recovery_frames < 1:
            raise ValueError("recovery needs at least one frame")


@dataclass(frozen=True)
class SupervisionEvent:
    name: str
    state: SupervisionState
    at_us: int


@dataclass
class _Track:
    message: SupervisedMessage
    state: SupervisionState = SupervisionState.WAITING
    last_seen_us: int | None = None
    good_frames: int = 0
    received: int = 0


@dataclass
class TimeoutMonitor:
    """Tracks each supervised message: WAITING until the first frame, then OK or TIMEOUT.

    A message in TIMEOUT returns to OK after `recovery_frames` consecutive frames.
    The monitor never transmits; it is a passive bench node.
    """

    messages: list[SupervisedMessage]
    start_us: int = 0
    events: list[SupervisionEvent] = field(default_factory=list)
    _tracks: dict[tuple[int, bool], _Track] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for message in self.messages:
            key = (message.arbitration_id, message.is_extended_id)
            if key in self._tracks:
                raise ValueError(f"message {message.name} is supervised twice")
            self._tracks[key] = _Track(message)

    def state(self, name: str) -> SupervisionState:
        for track in self._tracks.values():
            if track.message.name == name:
                return track.state
        raise KeyError(name)

    def received(self, name: str) -> int:
        for track in self._tracks.values():
            if track.message.name == name:
                return track.received
        raise KeyError(name)

    def _deadline(self, track: _Track) -> int:
        reference = self.start_us if track.last_seen_us is None else track.last_seen_us
        return reference + track.message.timeout_us

    def _set(self, track: _Track, state: SupervisionState, at_us: int) -> None:
        if track.state is not state:
            track.state = state
            self.events.append(SupervisionEvent(track.message.name, state, at_us))

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        self.poll(now_us)
        track = self._tracks.get((frame.arbitration_id, frame.is_extended_id))
        if track is None:
            return []
        track.received += 1
        track.last_seen_us = now_us
        if track.state is SupervisionState.TIMEOUT:
            track.good_frames += 1
            if track.good_frames >= track.message.recovery_frames:
                self._set(track, SupervisionState.OK, now_us)
        else:
            self._set(track, SupervisionState.OK, now_us)
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        # A message never seen is also reported once its first timeout expires.
        expired = sorted(
            (
                (self._deadline(track), track.message.name, track)
                for track in self._tracks.values()
                if track.state is not SupervisionState.TIMEOUT and now_us >= self._deadline(track)
            ),
            key=lambda item: (item[0], item[1]),
        )
        for deadline, _, track in expired:
            track.good_frames = 0
            self._set(track, SupervisionState.TIMEOUT, deadline)
        return []

    def next_deadline_us(self) -> int | None:
        deadlines = [
            self._deadline(track)
            for track in self._tracks.values()
            if track.state is not SupervisionState.TIMEOUT
        ]
        return min(deadlines) if deadlines else None
