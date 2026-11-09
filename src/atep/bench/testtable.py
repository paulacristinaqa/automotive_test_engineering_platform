"""Data-driven test tables, in the style of vTESTstudio test tables.

A table is a JSON file that a test engineer can edit without Python:

```json
{
  "module": "ACU loop boundaries",
  "tests": [
    {
      "id": "TT-001",
      "title": "Driver airbag loop at {ohm} ohm",
      "requirements": ["BENCH-F-040"],
      "parameters": [{"ohm": 1.4, "failure": "1A"}, {"ohm": 1.5, "failure": "none"}],
      "steps": [
        {"do": "switch_on"},
        {"do": "scpi", "address": "FIB", "command": "SOUR:RES {ohm},(@1)"},
        {"do": "wait", "ms": 600},
        {"do": "check_dtc", "dtc": "B1001", "failure": "{failure}"}
      ]
    }
  ]
}
```

Each parameter set becomes its own test case (`TT-001[1]`, `TT-001[2]`, ...).
`{name}` placeholders are replaced with the parameter value; a value that is
only a placeholder keeps the parameter's type.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atep.bench.airbag import AcuState, dtc_code, half_sine_pulse
from atep.bench.testunit import RegisteredCase, TestContext, TestModule, Verdict

PLACEHOLDER = re.compile(r"\{(\w+)\}")


class TestTableError(ValueError):
    """The table is not valid; the message names the test and step."""

    __test__ = False


def _as_text(value: object) -> str:
    """Placeholder text in JSON spelling: true, false, null."""
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    return str(value)


def substitute(value: Any, parameters: Mapping[str, object]) -> Any:
    if isinstance(value, str):
        whole = PLACEHOLDER.fullmatch(value)
        if whole and whole.group(1) in parameters:
            return parameters[whole.group(1)]
        return PLACEHOLDER.sub(
            lambda match: _as_text(parameters.get(match.group(1), match.group(0))), value
        )
    if isinstance(value, list):
        return [substitute(item, parameters) for item in value]
    if isinstance(value, dict):
        return {key: substitute(item, parameters) for key, item in value.items()}
    return value


def _failure_type(dtcs: dict[int, int], family: str) -> str:
    """Which failure type of a DTC family is currently failing: 'none' or e.g. '1A'."""
    base = dtc_code(family) >> 8
    active = sorted(
        code & 0xFF for code, status in dtcs.items() if code >> 8 == base and status & 1
    )
    return ",".join(f"{item:02X}" for item in active) or "none"


StepAction = Callable[[TestContext, dict[str, Any]], None]


def _switch_on(t: TestContext, step: dict[str, Any]) -> None:
    t.bench.switch_on(volts=float(step.get("volts", 12.0)))


def _ignition(t: TestContext, step: dict[str, Any]) -> None:
    command = "ROUT:CLOS (@1)" if step["on"] else "ROUT:OPEN (@1)"
    t.scpi("REL", command)


def _scpi(t: TestContext, step: dict[str, Any]) -> None:
    answer = t.scpi(step["address"], step["command"])
    if "expect" in step:
        t.check(f"{step['address']} {step['command']}", str(step["expect"]), answer)


def _wait(t: TestContext, step: dict[str, Any]) -> None:
    t.wait(float(step["ms"]))


def _expect_diag(t: TestContext, step: dict[str, Any]) -> None:
    nrc = step.get("nrc")
    t.expect_diag(
        step["request"],
        response_prefix=step.get("response_prefix"),
        nrc=int(nrc, 16) if isinstance(nrc, str) else nrc,
        description=step.get("description"),
    )


def _check_dtc(t: TestContext, step: dict[str, Any]) -> None:
    expected = str(step["failure"]).upper() if str(step["failure"]).lower() != "none" else "none"
    t.check(f"{step['dtc']} failing failure type", expected, _failure_type(t.dtcs(), step["dtc"]))


def _expect_signal(t: TestContext, step: dict[str, Any]) -> None:
    t.expect_signal(
        step["message"],
        step["signal"],
        low=float(step["low"]),
        high=float(step["high"]),
        timeout_ms=float(step["timeout_ms"]),
    )


def _check_state(t: TestContext, step: dict[str, Any]) -> None:
    t.check("ACU state", AcuState[str(step["state"]).upper()], t.bench.acu.state)


def _check_lamp(t: TestContext, step: dict[str, Any]) -> None:
    t.check("Warning lamp", bool(step["on"]), t.bench.acu.lamp_on)


def _occupancy(t: TestContext, step: dict[str, Any]) -> None:
    t.bench.acu.set_occupancy(
        t.bench.now_us,
        driver_buckled=step.get("driver_buckled"),
        passenger_occupied=step.get("passenger_occupied"),
        passenger_airbag_enabled=step.get("passenger_airbag_enabled"),
    )


def _crash(t: TestContext, step: dict[str, Any]) -> None:
    start = t.bench.now_us + round(float(step.get("delay_ms", 10)) * 1000)
    pulse = half_sine_pulse(
        start, peak_g=float(step["peak_g"]), duration_ms=int(step["duration_ms"])
    )
    t.bench.acu.inject_crash(pulse)


def _check_fired(t: TestContext, step: dict[str, Any]) -> None:
    crash = t.bench.acu.crash
    fired = sorted(loop.value for loop in crash.fired) if crash else []
    t.check("Fired loops", sorted(step["loops"]), fired)


ACTIONS: dict[str, StepAction] = {
    "switch_on": _switch_on,
    "ignition": _ignition,
    "scpi": _scpi,
    "wait": _wait,
    "expect_diag": _expect_diag,
    "check_dtc": _check_dtc,
    "expect_signal": _expect_signal,
    "check_state": _check_state,
    "check_lamp": _check_lamp,
    "occupancy": _occupancy,
    "crash": _crash,
    "check_fired": _check_fired,
}


@dataclass(frozen=True)
class TableTest:
    test_id: str
    title: str
    requirements: tuple[str, ...]
    steps: tuple[dict[str, Any], ...]
    parameters: tuple[dict[str, object], ...]


def _validate(test: dict[str, Any], index: int) -> TableTest:
    where = f"test {index + 1}"
    for key in ("id", "title", "steps"):
        if key not in test:
            raise TestTableError(f"{where}: missing '{key}'")
    where = f"test {test['id']}"
    steps = test["steps"]
    if not isinstance(steps, list) or not steps:
        raise TestTableError(f"{where}: 'steps' must be a non-empty list")
    for number, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise TestTableError(f"{where}, step {number}: a step must be an object, got {step!r}")
        action = step.get("do")
        if action not in ACTIONS:
            raise TestTableError(
                f"{where}, step {number}: unknown action {action!r}; use one of {sorted(ACTIONS)}"
            )
    parameters = test.get("parameters") or [{}]
    if not isinstance(parameters, list) or not all(isinstance(item, dict) for item in parameters):
        raise TestTableError(f"{where}: 'parameters' must be a list of objects")
    return TableTest(
        test_id=str(test["id"]),
        title=str(test["title"]),
        requirements=tuple(str(item) for item in test.get("requirements", [])),
        steps=tuple(steps),
        parameters=tuple(parameters),
    )


def _runner(
    steps: tuple[dict[str, Any], ...], parameters: dict[str, object]
) -> Callable[[TestContext], None]:
    def run(t: TestContext) -> None:
        for raw in steps:
            step = substitute(raw, parameters)
            ACTIONS[step["do"]](t, step)

    return run


def module_from_table(table: Mapping[str, Any]) -> TestModule:
    """Build a test module; every parameter set becomes its own test case."""
    if "tests" not in table or not isinstance(table["tests"], list):
        raise TestTableError("a test table needs a 'tests' list")
    module = TestModule(str(table.get("module", "Test table")))
    for index, raw in enumerate(table["tests"]):
        test = _validate(raw, index)
        many = len(test.parameters) > 1
        for number, parameters in enumerate(test.parameters, start=1):
            module.add(
                RegisteredCase(
                    case_id=f"{test.test_id}[{number}]" if many else test.test_id,
                    title=substitute(test.title, parameters),
                    requirements=test.requirements,
                    function=_runner(test.steps, parameters),
                    parameters=tuple(parameters.items()),
                )
            )
    return module


def load_test_table(path: Path) -> TestModule:
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise TestTableError(f"{path.name}: invalid JSON at line {error.lineno}") from error
    return module_from_table(table)


__all__ = ["ACTIONS", "TestTableError", "Verdict", "load_test_table", "module_from_table"]
