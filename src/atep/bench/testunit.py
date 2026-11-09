"""Event-driven test units for the virtual bench, in the style of vTESTstudio and CAPL.

A test module groups test cases. Each test case gets a fresh bench and a
`TestContext` with CAPL-like primitives:

| CAPL / vTESTstudio | TestContext |
|---|---|
| `TestStep`, `TestStepPass`, `TestStepFail` | `step`, `check` |
| `TestWaitForTimeout` | `wait` |
| `TestWaitForMessage` | `wait_for_message` |
| `TestWaitForSignalInRange` | `wait_for_signal` |
| `on message` | `on_message` |
| `on timer` | `on_timer` |
| Diagnostic request with expected response | `expect_diag` |

Verdicts follow vTESTstudio's worst-wins rule: error > fail > inconclusive > pass.
An exception inside a test case becomes an error step instead of stopping the module.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum

from atep.bench.airbag import SPEC, decode
from atep.bench.airbag_bench import HilBench
from atep.bench.campaign import CampaignReport, report_text
from atep.bench.uds import UdsOutcome, UdsResult
from atep.bench.vector_trace import TraceFrame


class Verdict(IntEnum):
    """Ordered so that the worst verdict is the maximum."""

    NONE = 0
    PASS = 1
    INCONCLUSIVE = 2
    FAIL = 3
    ERROR = 4

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class StepResult:
    ident: str
    description: str
    verdict: Verdict
    timestamp_us: int
    expected: str = ""
    actual: str = ""


@dataclass
class TestCaseResult:
    case_id: str
    title: str
    requirements: list[str]
    steps: list[StepResult] = field(default_factory=list)
    start_us: int = 0
    end_us: int = 0
    parameters: dict[str, object] = field(default_factory=dict)

    __test__ = False  # not a pytest test class

    @property
    def verdict(self) -> Verdict:
        if not self.steps:
            return Verdict.INCONCLUSIVE
        return max(step.verdict for step in self.steps)


@dataclass
class TestModuleResult:
    title: str
    cases: list[TestCaseResult] = field(default_factory=list)

    __test__ = False

    @property
    def verdict(self) -> Verdict:
        return max((case.verdict for case in self.cases), default=Verdict.NONE)

    def count(self, verdict: Verdict) -> int:
        return sum(1 for case in self.cases if case.verdict is verdict)


MESSAGE_IDS = {frame.identifier: frame.frame_id for frame in SPEC.frames}


def _message_id(message: str) -> int:
    key = message.replace("_", "-")
    if key not in MESSAGE_IDS:
        raise KeyError(f"unknown message {message}; known: {sorted(MESSAGE_IDS)}")
    return MESSAGE_IDS[key]


MessageHandler = Callable[[dict[str, Decimal], int], None]
TimerHandler = Callable[[int], None]


@dataclass
class EventNode:
    """Passive bench node that records frames and dispatches `on message` and `on timer`.

    Handlers run inside the bus simulation, like CAPL event procedures: they may
    record steps and send SCPI commands, but must not wait.
    """

    received: list[TraceFrame] = field(default_factory=list)
    message_handlers: list[tuple[int, str, MessageHandler]] = field(default_factory=list)
    timers: list[list[object]] = field(default_factory=list)

    def on_frame(self, frame: TraceFrame, now_us: int) -> list[TraceFrame]:
        if frame.is_error_frame:
            return []
        self.received.append(
            TraceFrame(now_us, frame.arbitration_id, frame.is_extended_id, frame.data)
        )
        for arbitration_id, contract, handler in list(self.message_handlers):
            if arbitration_id == frame.arbitration_id and contract in SPEC.messages:
                handler(decode(contract, frame.data), now_us)
        return []

    def poll(self, now_us: int) -> list[TraceFrame]:
        for timer in self.timers:
            next_at, period, handler = timer
            assert isinstance(next_at, int) and isinstance(period, int) and callable(handler)
            while next_at <= now_us:
                handler(next_at)
                next_at += period
            timer[0] = next_at
        return []

    def next_deadline_us(self) -> int | None:
        times = [timer[0] for timer in self.timers if isinstance(timer[0], int)]
        return min(times) if times else None


class TestContext:
    """What a test case can do on the bench. Times in the API are in milliseconds."""

    __test__ = False

    def __init__(self, bench: HilBench, result: TestCaseResult) -> None:
        self.bench = bench
        self.result = result
        self.events = EventNode()
        bench.link.nodes.append(self.events)
        self._step = 0

    # Time ---------------------------------------------------------------------

    @property
    def now_ms(self) -> float:
        return self.bench.now_us / 1000

    def wait(self, ms: float) -> None:
        self.bench.wait(round(ms * 1000))

    # Verdicts -----------------------------------------------------------------

    def step(
        self,
        description: str,
        verdict: Verdict = Verdict.PASS,
        *,
        expected: object = "",
        actual: object = "",
    ) -> None:
        self._step += 1
        self.result.steps.append(
            StepResult(
                ident=f"{self._step}",
                description=description,
                verdict=verdict,
                timestamp_us=self.bench.now_us,
                expected=report_text(expected) if expected != "" else "",
                actual=report_text(actual) if actual != "" else "",
            )
        )

    def check(
        self, description: str, expected: object, actual: object, *, at_most: bool = False
    ) -> bool:
        """Record a pass or fail step comparing actual with expected (or a limit)."""
        try:
            passed = bool(actual <= expected) if at_most else expected == actual  # type: ignore[operator]
        except TypeError:
            passed = False
        shown = f"<= {report_text(expected)}" if at_most else expected
        self.step(
            description, Verdict.PASS if passed else Verdict.FAIL, expected=shown, actual=actual
        )
        return passed

    def inconclusive(self, description: str) -> None:
        self.step(description, Verdict.INCONCLUSIVE)

    # Events -------------------------------------------------------------------

    def on_message(self, message: str, handler: MessageHandler) -> None:
        contract = message.replace("_", "-")
        self.events.message_handlers.append((_message_id(message), contract, handler))

    def on_timer(self, period_ms: float, handler: TimerHandler) -> None:
        period = round(period_ms * 1000)
        if period <= 0:
            raise ValueError("timer period must be positive")
        self.events.timers.append([self.bench.now_us + period, period, handler])

    def _await(self, found: Callable[[], bool], timeout_ms: float) -> bool:
        deadline = self.bench.now_us + round(timeout_ms * 1000)
        link = self.bench.link
        while not found():
            upcoming = link._next_time()
            if upcoming is None or upcoming > deadline:
                link.advance_to(deadline)
                return found()
            link.step()
        return True

    def wait_for_message(self, message: str, timeout_ms: float) -> dict[str, Decimal] | None:
        """Wait for the next frame of `message`; return its decoded signals or None."""
        arbitration_id = _message_id(message)
        start = len(self.events.received)

        def match() -> TraceFrame | None:
            for frame in self.events.received[start:]:
                if frame.arbitration_id == arbitration_id:
                    return frame
            return None

        if not self._await(lambda: match() is not None, timeout_ms):
            return None
        frame = match()
        assert frame is not None
        return decode(message.replace("_", "-"), frame.data)

    def wait_for_signal(
        self, message: str, signal: str, *, low: float, high: float, timeout_ms: float
    ) -> Decimal | None:
        """Wait until a `message` frame carries `signal` within [low, high]."""
        arbitration_id = _message_id(message)
        contract = message.replace("_", "-")
        start = len(self.events.received)
        value: list[Decimal] = []

        def match() -> bool:
            for frame in self.events.received[start:]:
                if frame.arbitration_id != arbitration_id:
                    continue
                candidate = decode(contract, frame.data)[signal]
                if Decimal(str(low)) <= candidate <= Decimal(str(high)):
                    value.append(candidate)
                    return True
            return False

        return value[0] if self._await(match, timeout_ms) else None

    def expect_signal(
        self, message: str, signal: str, *, low: float, high: float, timeout_ms: float
    ) -> bool:
        value = self.wait_for_signal(message, signal, low=low, high=high, timeout_ms=timeout_ms)
        expected = f"{low}..{high} within {timeout_ms:g} ms"
        description = f"{message}.{signal} reaches {low}..{high}"
        if value is None:
            self.step(description, Verdict.FAIL, expected=expected, actual="timeout")
            return False
        self.step(description, Verdict.PASS, expected=expected, actual=value)
        return True

    # Bench access ---------------------------------------------------------------

    def scpi(self, address: str, command: str) -> str | None:
        return self.bench.scpi(address, command)

    def diag(self, request_hex: str) -> UdsResult:
        return self.bench.ask(request_hex)

    def expect_diag(
        self,
        request_hex: str,
        *,
        response_prefix: str | None = None,
        nrc: int | None = None,
        description: str | None = None,
    ) -> UdsResult:
        result = self.diag(request_hex)
        text = description or f"Diagnostic request {request_hex}"
        if nrc is not None:
            ok = result.outcome is UdsOutcome.NEGATIVE and result.nrc == nrc
            expected: object = f"NRC 0x{nrc:02X}"
            actual: object = f"NRC 0x{result.nrc:02X}" if result.nrc is not None else result.outcome
        else:
            prefix = bytes.fromhex(response_prefix or "")
            ok = result.outcome is UdsOutcome.POSITIVE and result.response.startswith(prefix)
            expected = f"positive, starts {prefix.hex(' ').upper()}"
            actual = result.response if result.response else result.outcome
        self.step(text, Verdict.PASS if ok else Verdict.FAIL, expected=expected, actual=actual)
        return result

    def dtcs(self) -> dict[int, int]:
        return self.bench.read_dtcs()


TestFunction = Callable[[TestContext], None]


@dataclass(frozen=True)
class RegisteredCase:
    case_id: str
    title: str
    requirements: tuple[str, ...]
    function: TestFunction
    parameters: tuple[tuple[str, object], ...] = ()


class TestModule:
    """A named set of test cases; each case runs on a fresh bench."""

    __test__ = False

    def __init__(self, title: str, bench_factory: Callable[[], HilBench] = HilBench) -> None:
        self.title = title
        self.bench_factory = bench_factory
        self.cases: list[RegisteredCase] = []

    def test_case(
        self, case_id: str, title: str, *, requirements: tuple[str, ...] = ()
    ) -> Callable[[TestFunction], TestFunction]:
        def register(function: TestFunction) -> TestFunction:
            self.add(RegisteredCase(case_id, title, requirements, function))
            return function

        return register

    def add(self, case: RegisteredCase) -> None:
        if any(existing.case_id == case.case_id for existing in self.cases):
            raise ValueError(f"duplicate test case id {case.case_id}")
        self.cases.append(case)

    def run(self, bench_factory: Callable[[], HilBench] | None = None) -> TestModuleResult:
        """Run every case on a fresh bench from `bench_factory` (default: the module's own)."""
        factory = bench_factory or self.bench_factory
        module = TestModuleResult(self.title)
        for case in self.cases:
            module.cases.append(run_test_case(case, factory()))
        return module


def run_test_case(case: RegisteredCase, bench: HilBench) -> TestCaseResult:
    result = TestCaseResult(
        case.case_id,
        case.title,
        list(case.requirements),
        start_us=bench.now_us,
        parameters=dict(case.parameters),
    )
    context = TestContext(bench, result)
    try:
        case.function(context)
    except Exception as error:  # a broken test is an error verdict, not a crash
        context.step(f"Test case raised {type(error).__name__}: {error}", Verdict.ERROR)
    result.end_us = bench.now_us
    return result


def module_from_campaign(report: CampaignReport) -> TestModuleResult:
    """Express a campaign (checks per case) as a test module (steps per case)."""
    module = TestModuleResult(report.title)
    for case in report.cases:
        result = TestCaseResult(case.case_id, case.title, list(case.requirements))
        for index, check in enumerate(case.checks, start=1):
            result.steps.append(
                StepResult(
                    ident=str(index),
                    description=check.name,
                    verdict=Verdict.PASS if check.passed else Verdict.FAIL,
                    timestamp_us=0,
                    expected=check.expected_text,
                    actual=report_text(check.actual),
                )
            )
        module.cases.append(result)
    return module
