from decimal import Decimal

import pytest

from atep.bench.airbag_bench import HilBench
from atep.bench.campaign import CampaignReport, CaseResult, Check
from atep.bench.testunit import (
    RegisteredCase,
    StepResult,
    TestCaseResult,
    TestContext,
    TestModule,
    TestModuleResult,
    Verdict,
    module_from_campaign,
    run_test_case,
)


def _run(function) -> TestCaseResult:  # type: ignore[no-untyped-def]
    return run_test_case(RegisteredCase("T-1", "case", ("REQ",), function), HilBench())


def _power_up(t: TestContext) -> None:
    t.bench.switch_on()


def test_verdicts_are_ordered_worst_last() -> None:
    assert Verdict.NONE < Verdict.PASS < Verdict.INCONCLUSIVE < Verdict.FAIL < Verdict.ERROR
    assert Verdict.ERROR.label == "error"
    case = TestCaseResult("T", "t", [])
    assert case.verdict is Verdict.INCONCLUSIVE  # no step, no verdict
    case.steps += [
        StepResult("1", "a", Verdict.PASS, 0),
        StepResult("2", "b", Verdict.INCONCLUSIVE, 0),
    ]
    assert case.verdict is Verdict.INCONCLUSIVE
    case.steps.append(StepResult("3", "c", Verdict.FAIL, 0))
    module = TestModuleResult("m", [case])
    assert (module.verdict, module.count(Verdict.FAIL)) == (Verdict.FAIL, 1)
    assert TestModuleResult("empty").verdict is Verdict.NONE


def test_checks_limits_and_incomparable_values() -> None:
    def body(t: TestContext) -> None:
        t.check("equal", 1, 1)
        t.check("limit", 10, 9, at_most=True)
        t.check("limit exceeded", 10, 11, at_most=True)
        t.check("incomparable", 10, "x", at_most=True)
        t.inconclusive("could not decide")

    result = _run(body)
    assert [step.verdict for step in result.steps] == [
        Verdict.PASS,
        Verdict.PASS,
        Verdict.FAIL,
        Verdict.FAIL,
        Verdict.INCONCLUSIVE,
    ]
    assert result.steps[1].expected == "<= 10"
    assert [step.ident for step in result.steps] == ["1", "2", "3", "4", "5"]


def test_an_exception_becomes_an_error_step() -> None:
    def body(t: TestContext) -> None:
        t.check("before", 1, 1)
        raise RuntimeError("bench cable unplugged")

    result = _run(body)
    assert result.verdict is Verdict.ERROR
    assert result.steps[-1].description == "Test case raised RuntimeError: bench cable unplugged"


def test_wait_for_message_times_out_exactly_and_returns_signals_otherwise() -> None:
    seen: dict[str, object] = {}

    def body(t: TestContext) -> None:
        start = t.now_ms
        seen["missing"] = t.wait_for_message("acu_status", 250)
        seen["waited"] = t.now_ms - start
        _power_up(t)
        seen["status"] = t.wait_for_message("acu_status", 150)
        seen["lamp"] = t.wait_for_signal("acu_status", "WarningLamp", low=0, high=0, timeout_ms=150)

    _run(body)
    assert seen["missing"] is None and seen["waited"] == 250
    status = seen["status"]
    assert isinstance(status, dict) and status["SystemState"] == Decimal(2)
    assert seen["lamp"] == Decimal(0)


def test_expect_signal_and_expect_diag_record_steps() -> None:
    def body(t: TestContext) -> None:
        _power_up(t)
        t.expect_signal("acu_status", "CrashStored", low=1, high=1, timeout_ms=200)
        t.expect_diag("22F190", response_prefix="62F190")
        t.expect_diag("22F190", response_prefix="62F191")
        t.expect_diag("2701", nrc=0x7F)
        t.expect_diag("22F190", nrc=0x31)

    result = _run(body)
    verdicts = [step.verdict for step in result.steps]
    assert verdicts == [Verdict.FAIL, Verdict.PASS, Verdict.FAIL, Verdict.PASS, Verdict.FAIL]
    assert result.steps[0].actual == "timeout"
    assert result.steps[3].actual == "NRC 0x7F"


def test_message_and_timer_handlers() -> None:
    counts = {"status": 0, "timer": 0}

    def body(t: TestContext) -> None:
        _power_up(t)
        t.on_message(
            "acu-status", lambda signals, now: counts.__setitem__("status", counts["status"] + 1)
        )
        t.on_timer(25, lambda now: counts.__setitem__("timer", counts["timer"] + 1))
        t.wait(1_000)
        with pytest.raises(ValueError):
            t.on_timer(0, lambda now: None)
        with pytest.raises(KeyError):
            t.on_message("no_such_message", lambda signals, now: None)
        t.check("handlers ran", True, counts["status"] > 0)

    result = _run(body)
    assert result.verdict is Verdict.PASS
    assert counts == {"status": 10, "timer": 40}


def test_module_runs_each_case_on_a_fresh_bench_and_rejects_duplicates() -> None:
    module = TestModule("m")
    benches: list[HilBench] = []

    @module.test_case("A", "first", requirements=("R1",))
    def first(t: TestContext) -> None:
        benches.append(t.bench)
        t.check("ok", 1, 1)

    @module.test_case("B", "second")
    def second(t: TestContext) -> None:
        benches.append(t.bench)
        t.check("ok", 1, 2)

    result = module.run()
    assert benches[0] is not benches[1]
    assert [case.verdict for case in result.cases] == [Verdict.PASS, Verdict.FAIL]
    assert result.cases[0].requirements == ["R1"]
    with pytest.raises(ValueError, match="duplicate"):
        module.add(RegisteredCase("A", "again", (), first))


def test_campaigns_convert_to_modules() -> None:
    campaign = CampaignReport(
        "campaign",
        [CaseResult("C-1", "case", ["R"], [Check("a", 1, 1), Check("b", 5, 6, at_most=True)])],
    )
    module = module_from_campaign(campaign)
    case = module.cases[0]
    assert (module.title, case.case_id, case.requirements) == ("campaign", "C-1", ["R"])
    assert [(s.verdict, s.expected, s.actual) for s in case.steps] == [
        (Verdict.PASS, "1", "1"),
        (Verdict.FAIL, "<= 5", "6"),
    ]
