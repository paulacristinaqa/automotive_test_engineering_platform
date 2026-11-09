"""Virtual HiL bench instruments driven by SCPI, wired to the virtual ACU.

| Address | Instrument | Drives |
|---|---|---|
| PSU | Programmable power supply | KL30 voltage, voltage profiles, current readback |
| REL | Relay card | KL15 (ignition) on channel 1 |
| FIB | Fault-injection box | Squib loops 1-4: open, short to GND/battery, resistance |
| DMM | Digital multimeter | Terminal voltage, supply current, loop resistance |
| CHAM | Climate chamber | ACU and harness temperature, with a ramp rate |

Voltage profiles follow the shape of ISO 16750-2 tests with shortened durations
so a campaign runs in seconds of logical time. They are not certified test levels.
"""

import math
from dataclasses import dataclass, field
from typing import Protocol

from atep.bench.airbag import AirbagControlUnit, Loop, LoopShort
from atep.bench.scpi import (
    DATA_OUT_OF_RANGE,
    EXECUTION_ERROR,
    UNDEFINED_HEADER,
    Instrument,
    ScpiCommand,
    ScpiError,
    format_number,
)
from atep.bench.vector_trace import TraceFrame

NOMINAL_LOOP_OHM = 2.2
LOOP_CHANNELS = {
    1: Loop.DRIVER_AIRBAG,
    2: Loop.PASSENGER_AIRBAG,
    3: Loop.DRIVER_PRETENSIONER,
    4: Loop.PASSENGER_PRETENSIONER,
}


@dataclass(frozen=True)
class VoltageProfile:
    """Voltage over time as breakpoints (offset µs, volts), linear between them.

    Two breakpoints at the same offset make a step.
    """

    name: str
    description: str
    points: tuple[tuple[int, float], ...]
    step_us: int = 10_000

    def __post_init__(self) -> None:
        if not self.points or self.points[0][0] != 0:
            raise ValueError("a profile starts at offset 0")
        offsets = [offset for offset, _ in self.points]
        if offsets != sorted(offsets):
            raise ValueError("profile offsets must not go backwards")
        if any(volts < 0 or volts > 60 for _, volts in self.points):
            raise ValueError("profile voltages must be between 0 and 60 V")

    @property
    def duration_us(self) -> int:
        return self.points[-1][0]

    def voltage_at(self, offset_us: int) -> float:
        """Value at an offset; at a step the later breakpoint wins."""
        value = self.points[0][1]
        for (t0, v0), (t1, v1) in zip(self.points, self.points[1:], strict=False):
            if offset_us >= t1:
                value = v1
            elif t0 <= offset_us < t1:
                return v0 + (v1 - v0) * (offset_us - t0) / (t1 - t0)
        return value

    def sample_offsets(self) -> list[int]:
        """Every breakpoint plus a sample each `step_us` inside ramps."""
        offsets = {offset for offset, _ in self.points}
        for (t0, v0), (t1, v1) in zip(self.points, self.points[1:], strict=False):
            if v0 != v1 and t1 > t0:
                offsets.update(range(t0, t1, self.step_us))
        return sorted(offsets)


def momentary_drop(
    *, nominal_v: float = 12.0, drop_v: float = 4.5, duration_ms: int = 100
) -> VoltageProfile:
    return VoltageProfile(
        "momentary_drop",
        f"ISO 16750-2-style momentary drop to {drop_v} V for {duration_ms} ms",
        (
            (0, nominal_v),
            (0, drop_v),
            (duration_ms * 1000, drop_v),
            (duration_ms * 1000, nominal_v),
        ),
    )


def dropout(*, nominal_v: float = 12.0, duration_ms: int = 300) -> VoltageProfile:
    return VoltageProfile(
        "dropout",
        f"Supply interruption to 0 V for {duration_ms} ms",
        ((0, nominal_v), (0, 0.0), (duration_ms * 1000, 0.0), (duration_ms * 1000, nominal_v)),
    )


def starting_profile(
    *,
    nominal_v: float = 12.0,
    crank_v: float = 4.5,
    crank_ms: int = 15,
    run_v: float = 6.5,
    run_ms: int = 1000,
) -> VoltageProfile:
    """Engine start: a short deep dip, a longer plateau, then recovery (simplified shape)."""
    t1 = 5_000
    t2 = t1 + crank_ms * 1000
    t3 = t2 + 50_000
    t4 = t3 + run_ms * 1000
    t5 = t4 + 100_000
    return VoltageProfile(
        "starting_profile",
        f"Starting profile: {crank_v} V for {crank_ms} ms, {run_v} V for {run_ms} ms",
        ((0, nominal_v), (t1, crank_v), (t2, crank_v), (t3, run_v), (t4, run_v), (t5, nominal_v)),
        step_us=5_000,
    )


def slow_decrease_increase(
    *, nominal_v: float = 12.0, minimum_v: float = 0.0, rate_v_per_s: float = 1.0
) -> VoltageProfile:
    """Slow ramp down to `minimum_v` and back (ISO uses 0.5 V/min; shortened here)."""
    ramp_us = round((nominal_v - minimum_v) / rate_v_per_s * 1_000_000)
    return VoltageProfile(
        "slow_decrease_increase",
        f"Slow decrease to {minimum_v} V and increase at {rate_v_per_s} V/s",
        (
            (0, nominal_v),
            (ramp_us, minimum_v),
            (ramp_us + 1_000_000, minimum_v),
            (2 * ramp_us + 1_000_000, nominal_v),
        ),
        step_us=50_000,
    )


def overvoltage(
    *, nominal_v: float = 12.0, level_v: float = 18.0, duration_s: float = 3.0
) -> VoltageProfile:
    """Long-term overvoltage (ISO uses 18 V for 60 min; shortened here)."""
    duration = round(duration_s * 1_000_000)
    return VoltageProfile(
        "overvoltage",
        f"Overvoltage {level_v} V for {duration_s} s",
        ((0, nominal_v), (0, level_v), (duration, level_v), (duration, nominal_v)),
    )


def standard_profiles() -> dict[str, VoltageProfile]:
    profiles = [
        momentary_drop(),
        dropout(),
        starting_profile(),
        slow_decrease_increase(),
        overvoltage(),
    ]
    return {profile.name: profile for profile in profiles}


class PowerSupply(Instrument):
    """KL30 supply. Also a bench node, so profiles run on logical time."""

    identity = "ATEP,VIRTUAL-PSU-60V,0001,1.0"

    def __init__(
        self, acu: AirbagControlUnit, profiles: dict[str, VoltageProfile] | None = None
    ) -> None:
        super().__init__()
        self.acu = acu
        self.profiles = profiles or standard_profiles()
        self.setpoint_v = 12.0
        self.output = False
        self.peak_since_us = 0
        self._running: VoltageProfile | None = None
        self._started_us = 0
        self._samples: list[int] = []

    @property
    def output_v(self) -> float:
        return self.setpoint_v if self.output else 0.0

    def _apply(self, now_us: int) -> None:
        self.acu.set_power(now_us, kl30_v=self.output_v)

    def reset(self, now_us: int) -> None:
        self._running = None
        self.setpoint_v = 12.0
        self.output = False
        self._apply(now_us)

    def run_profile(self, name: str, now_us: int) -> None:
        profile = self.profiles.get(name.lower())
        if profile is None:
            raise ScpiError(DATA_OUT_OF_RANGE, "Unknown profile")
        if not self.output:
            raise ScpiError(EXECUTION_ERROR, "Output is off")
        self._running = profile
        self._started_us = now_us
        self._samples = [now_us + offset for offset in profile.sample_offsets()]
        self.poll(now_us)

    def handle(self, command: ScpiCommand, now_us: int) -> str | None:
        header = command.header
        if header == "OUTP:STAT":  # [:STATe] is an optional SCPI node
            header = "OUTP"
        if header == "VOLT":
            if command.query:
                return format_number(self.setpoint_v)
            self.setpoint_v = command.number(minimum=0.0, maximum=60.0)
            self._running = None
            self._apply(now_us)
            return None
        if header == "OUTP":
            if command.query:
                return "1" if self.output else "0"
            self.output = command.boolean()
            self._running = None
            self._apply(now_us)
            return None
        if header == "MEAS:VOLT" and command.query:
            return format_number(self.output_v)
        if header == "MEAS:CURR" and command.query:
            return format_number(self.acu.supply_current_a() if self.output else 0.0)
        if header == "MEAS:CURR:PEAK" and command.query:
            return format_number(self.acu.peak_supply_current_a(self.peak_since_us))
        if header == "SENS:CURR:PEAK:CLE":
            self.peak_since_us = now_us
            return None
        if header == "PROG:RUN":
            if not command.args:
                raise ScpiError(DATA_OUT_OF_RANGE, "Missing profile name")
            self.run_profile(command.args[0], now_us)
            return None
        if header == "PROG:STAT" and command.query:
            return "RUNNING" if self._running else "IDLE"
        if header == "PROG:CAT" and command.query:
            return ",".join(sorted(self.profiles))
        raise ScpiError(UNDEFINED_HEADER, "Undefined header")

    # Bench node --------------------------------------------------------------

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        profile = self._running
        if profile is None:
            return []
        while self._samples and self._samples[0] <= now_us:
            at_us = self._samples.pop(0)
            self.setpoint_v = profile.voltage_at(at_us - self._started_us)
            self.acu.set_power(at_us, kl30_v=self.output_v)
        if not self._samples:
            self._running = None
        return []

    def next_deadline_us(self) -> int | None:
        return self._samples[0] if self._running and self._samples else None


class RelayCard(Instrument):
    """Channel 1 switches KL15 (ignition)."""

    identity = "ATEP,VIRTUAL-RELAY-8CH,0002,1.0"

    def __init__(self, acu: AirbagControlUnit) -> None:
        super().__init__()
        self.acu = acu
        self.closed: set[int] = set()

    def reset(self, now_us: int) -> None:
        self.closed.clear()
        self.acu.set_power(now_us, kl15=False)

    def handle(self, command: ScpiCommand, now_us: int) -> str | None:
        channels = command.channels(valid=range(1, 9))
        if command.header == "ROUT:CLOS" and command.query:
            return ",".join("1" if channel in self.closed else "0" for channel in channels)
        if command.header not in {"ROUT:CLOS", "ROUT:OPEN"} or command.query:
            raise ScpiError(UNDEFINED_HEADER, "Undefined header")
        for channel in channels:
            if command.header == "ROUT:CLOS":
                self.closed.add(channel)
            else:
                self.closed.discard(channel)
        self.acu.set_power(now_us, kl15=1 in self.closed)
        return None


@dataclass
class _LoopState:
    mode: str = "NOMINAL"
    ohms: float = NOMINAL_LOOP_OHM


class FaultInjectionBox(Instrument):
    """Breakout box between ACU and squib loads: one channel per loop."""

    identity = "ATEP,VIRTUAL-FIB-4CH,0003,1.0"

    def __init__(self, acu: AirbagControlUnit) -> None:
        super().__init__()
        self.acu = acu
        self.state: dict[int, _LoopState] = {channel: _LoopState() for channel in LOOP_CHANNELS}

    def _set(self, channel: int, now_us: int, mode: str, ohms: float, short: LoopShort) -> None:
        self.state[channel] = _LoopState(mode, ohms)
        loop = LOOP_CHANNELS[channel]
        self.acu.set_loop_short(now_us, loop, short)
        self.acu.set_loop_resistance(now_us, loop, ohms)

    def reset(self, now_us: int) -> None:
        for channel in LOOP_CHANNELS:
            self._set(channel, now_us, "NOMINAL", NOMINAL_LOOP_OHM, LoopShort.NONE)

    def handle(self, command: ScpiCommand, now_us: int) -> str | None:
        channels = command.channels(valid=range(1, 5))
        header = command.header
        if header == "ROUT:STAT" and command.query:
            parts = []
            for channel in channels:
                state = self.state[channel]
                parts.append(f"RES {state.ohms:.3f}" if state.mode == "RES" else state.mode)
            return ",".join(parts)
        if command.query:
            raise ScpiError(UNDEFINED_HEADER, "Undefined header")
        for channel in channels:
            if header == "ROUT:CLOS":
                self._set(channel, now_us, "NOMINAL", NOMINAL_LOOP_OHM, LoopShort.NONE)
            elif header == "ROUT:OPEN":
                self._set(channel, now_us, "OPEN", math.inf, LoopShort.NONE)
            elif header == "ROUT:SHOR:GND":
                self._set(channel, now_us, "SHORT GND", NOMINAL_LOOP_OHM, LoopShort.GROUND)
            elif header == "ROUT:SHOR:BATT":
                self._set(channel, now_us, "SHORT BATT", NOMINAL_LOOP_OHM, LoopShort.BATTERY)
            elif header == "SOUR:RES":
                ohms = command.number(0, minimum=0.0, maximum=1000.0)
                self._set(channel, now_us, "RES", ohms, LoopShort.NONE)
            else:
                raise ScpiError(UNDEFINED_HEADER, "Undefined header")
        return None


class Multimeter(Instrument):
    identity = "ATEP,VIRTUAL-DMM-6.5,0004,1.0"

    def __init__(self, acu: AirbagControlUnit) -> None:
        super().__init__()
        self.acu = acu

    def handle(self, command: ScpiCommand, now_us: int) -> str | None:
        if not command.query:
            raise ScpiError(UNDEFINED_HEADER, "Undefined header")
        if command.header == "MEAS:VOLT:DC":
            return format_number(self.acu.kl30_v)
        if command.header == "MEAS:CURR:DC":
            return format_number(self.acu.supply_current_a())
        if command.header == "MEAS:RES":
            channel = command.channels(valid=range(1, 5))[0]
            return format_number(self.acu.effective_resistance(LOOP_CHANNELS[channel]))
        raise ScpiError(UNDEFINED_HEADER, "Undefined header")


class ClimateChamber(Instrument):
    """Temperature setpoint reached with a ramp rate; a bench node on logical time."""

    identity = "ATEP,VIRTUAL-CHAMBER,0005,1.0"
    step_us = 1_000_000

    def __init__(self, acu: AirbagControlUnit) -> None:
        super().__init__()
        self.acu = acu
        self.temperature_c = 25.0
        self.setpoint_c = 25.0
        self.rate_c_per_min = 60.0
        self._next_at: int | None = None

    def reset(self, now_us: int) -> None:
        self.setpoint_c = 25.0
        self.temperature_c = 25.0
        self._next_at = None
        self.acu.set_temperature(now_us, 25.0)

    def handle(self, command: ScpiCommand, now_us: int) -> str | None:
        if command.header == "TEMP":
            if command.query:
                return format_number(self.temperature_c)
            self.setpoint_c = command.number(minimum=-70.0, maximum=180.0)
            # The air needs a full ramp step before the first change is felt.
            self._next_at = now_us + self.step_us
            return None
        if command.header == "TEMP:SETP" and command.query:
            return format_number(self.setpoint_c)
        if command.header == "TEMP:RATE":
            if command.query:
                return format_number(self.rate_c_per_min)
            self.rate_c_per_min = command.number(minimum=0.1, maximum=1000.0)
            return None
        raise ScpiError(UNDEFINED_HEADER, "Undefined header")

    @property
    def stable(self) -> bool:
        return self._next_at is None

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        while self._next_at is not None and self._next_at <= now_us:
            step = self.rate_c_per_min / 60 * self.step_us / 1_000_000
            difference = self.setpoint_c - self.temperature_c
            if abs(difference) <= step:
                self.temperature_c = self.setpoint_c
                self._next_at = None
            else:
                self.temperature_c += math.copysign(step, difference)
                self._next_at += self.step_us
            self.acu.set_temperature(now_us, self.temperature_c)
        return []

    def next_deadline_us(self) -> int | None:
        return self._next_at


class RackClock(Protocol):
    """Anything with a `now_us` attribute, such as a SimulatedLink."""

    now_us: int


@dataclass(frozen=True)
class ScpiLogEntry:
    at_us: int
    address: str
    command: str
    response: str | None


@dataclass
class BenchRack:
    """Instruments by address, with a log of every command like a HiL test log."""

    instruments: dict[str, Instrument]
    clock: RackClock
    log: list[ScpiLogEntry] = field(default_factory=list)

    def send(self, address: str, command: str) -> str | None:
        instrument = self.instruments.get(address.upper())
        if instrument is None:
            raise KeyError(f"no instrument at address {address}")
        now = self.clock.now_us
        response = instrument.execute(command, now)
        self.log.append(ScpiLogEntry(now, address.upper(), command, response))
        return response

    def query_float(self, address: str, command: str) -> float:
        response = self.send(address, command)
        if response is None:
            error = self.send(address, "SYST:ERR?")
            raise RuntimeError(f"{address} gave no answer to {command}: {error}")
        return float(response)

    def log_text(self) -> str:
        lines = []
        for entry in self.log:
            seconds = f"{entry.at_us / 1_000_000:12.6f}"
            answer = "" if entry.response is None else f" -> {entry.response}"
            lines.append(f"{seconds} {entry.address:<4} {entry.command}{answer}")
        return "\n".join(lines) + "\n"
