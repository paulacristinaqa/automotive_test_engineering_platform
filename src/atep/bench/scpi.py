"""A small SCPI (IEEE 488.2 / SCPI-99) command layer for bench instruments.

Real HiL racks drive power supplies, multimeters and relay cards with SCPI
strings such as `VOLT 12.5` or `MEAS:CURR?`. This module parses those strings,
accepts long and short mnemonics, and keeps an error queue read with
`SYST:ERR?`, so bench scripts look and fail like the real thing.
"""

from collections import deque
from dataclasses import dataclass

NO_ERROR = (0, "No error")
COMMAND_ERROR = -100
MISSING_PARAMETER = -109
UNDEFINED_HEADER = -113
EXECUTION_ERROR = -200
DATA_OUT_OF_RANGE = -222
ILLEGAL_PARAMETER_VALUE = -224
OVERLOAD = "9.9E37"  # SCPI value for an over-range reading

# Long SCPI mnemonics and their short forms (the upper-case part of the long form).
LONG_FORMS = {
    "BATTERY": "BATT",
    "CATALOG": "CAT",
    "CLEAR": "CLE",
    "CLOSE": "CLOS",
    "CURRENT": "CURR",
    "ERROR": "ERR",
    "GROUND": "GND",
    "MEASURE": "MEAS",
    "OUTPUT": "OUTP",
    "PROGRAM": "PROG",
    "RESISTANCE": "RES",
    "ROUTE": "ROUT",
    "SENSE": "SENS",
    "SETPOINT": "SETP",
    "SHORT": "SHOR",
    "SOURCE": "SOUR",
    "STATE": "STAT",
    "STATUS": "STAT",
    "SYSTEM": "SYST",
    "TEMPERATURE": "TEMP",
    "COUNT": "COUN",
    "LEVEL": "LEV",
    "PULSE": "PULS",
    "SELECT": "SEL",
    "WIDTH": "WIDT",
    "VOLTAGE": "VOLT",
}


class ScpiError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(f'{code},"{message}"')
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ScpiCommand:
    header: str
    query: bool
    args: tuple[str, ...]

    def number(self, index: int = 0, *, minimum: float, maximum: float) -> float:
        if len(self.args) <= index:
            raise ScpiError(MISSING_PARAMETER, "Missing parameter")
        try:
            value = float(self.args[index])
        except ValueError as error:
            raise ScpiError(ILLEGAL_PARAMETER_VALUE, "Illegal parameter value") from error
        if not minimum <= value <= maximum:
            raise ScpiError(DATA_OUT_OF_RANGE, "Data out of range")
        return value

    def boolean(self, index: int = 0) -> bool:
        if len(self.args) <= index:
            raise ScpiError(MISSING_PARAMETER, "Missing parameter")
        value = self.args[index].upper()
        if value in {"ON", "1"}:
            return True
        if value in {"OFF", "0"}:
            return False
        raise ScpiError(ILLEGAL_PARAMETER_VALUE, "Illegal parameter value")

    def channels(self, *, valid: range) -> list[int]:
        for arg in self.args:
            if arg.startswith("(@") and arg.endswith(")"):
                return parse_channel_list(arg, valid=valid)
        raise ScpiError(MISSING_PARAMETER, "Missing channel list")


def _split_args(text: str) -> tuple[str, ...]:
    args: list[str] = []
    depth = 0
    current = ""
    for character in text:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if character == "," and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += character
    if current.strip():
        args.append(current.strip())
    return tuple(args)


def parse_command(text: str) -> ScpiCommand:
    stripped = text.strip()
    if not stripped:
        raise ScpiError(COMMAND_ERROR, "Command error")
    head, _, rest = stripped.partition(" ")
    query = head.endswith("?")
    head = head.rstrip("?")
    if head.startswith("*"):
        return ScpiCommand(head.upper(), query, _split_args(rest))
    nodes = [node for node in head.lstrip(":").upper().split(":") if node]
    if not nodes:
        raise ScpiError(COMMAND_ERROR, "Command error")
    header = ":".join(LONG_FORMS.get(node, node) for node in nodes)
    return ScpiCommand(header, query, _split_args(rest))


def parse_channel_list(text: str, *, valid: range) -> list[int]:
    """Parse `(@1)`, `(@1,3)` or `(@1:4)` into channel numbers."""
    body = text.strip()[2:-1]
    channels: list[int] = []
    try:
        for part in body.split(","):
            if ":" in part:
                low, high = (int(item) for item in part.split(":"))
                channels.extend(range(low, high + 1))
            else:
                channels.append(int(part))
    except ValueError as error:
        raise ScpiError(ILLEGAL_PARAMETER_VALUE, "Illegal channel list") from error
    if not channels or any(channel not in valid for channel in channels):
        raise ScpiError(DATA_OUT_OF_RANGE, "Channel out of range")
    return channels


def format_number(value: float) -> str:
    if value != value or abs(value) >= 9.9e37:
        return OVERLOAD
    return f"{value:.6E}"


class Instrument:
    """Base instrument: IEEE 488.2 common commands and the SCPI error queue."""

    identity = "ATEP,VIRTUAL-INSTRUMENT,0,1.0"

    def __init__(self) -> None:
        self.errors: deque[tuple[int, str]] = deque(maxlen=20)

    def reset(self, now_us: int) -> None:
        """`*RST`: return to the power-on state."""

    def handle(self, command: ScpiCommand, now_us: int) -> str | None:
        raise ScpiError(UNDEFINED_HEADER, "Undefined header")

    def execute(self, text: str, now_us: int) -> str | None:
        """Run one command. Queries return their answer; errors go to the queue."""
        try:
            command = parse_command(text)
            if command.header == "*IDN" and command.query:
                return self.identity
            if command.header == "*RST":
                self.reset(now_us)
                return None
            if command.header == "*CLS":
                self.errors.clear()
                return None
            if command.header == "*OPC" and command.query:
                return "1"
            if command.header == "SYST:ERR" and command.query:
                code, message = self.errors.popleft() if self.errors else NO_ERROR
                return f'{code},"{message}"'
            return self.handle(command, now_us)
        except ScpiError as error:
            self.errors.append((error.code, error.message))
            return None
