import json
from pathlib import Path

import pytest

from atep.bench.testtable import (
    ACTIONS,
    TestTableError,
    _failure_type,
    load_test_table,
    module_from_table,
    substitute,
)
from atep.bench.testunit import Verdict

TABLE = Path(__file__).resolve().parent.parent / "tools" / "test_tables" / "acu_system_tests.json"


def test_substitution_keeps_types_for_whole_placeholders() -> None:
    parameters = {"ohm": 1.4, "on": True, "loops": ["a"], "name": "x"}
    assert substitute("{ohm}", parameters) == 1.4
    assert substitute("{on}", parameters) is True
    assert substitute("SOUR:RES {ohm},(@1)", parameters) == "SOUR:RES 1.4,(@1)"
    assert substitute("enabled={on}", parameters) == "enabled=true"
    assert substitute({"x": ["{loops}", "{missing}"]}, parameters) == {"x": [["a"], "{missing}"]}
    assert substitute(5, parameters) == 5


def test_failure_type_of_a_dtc_family() -> None:
    dtcs = {0x90011A: 0x2D, 0x90011B: 0x2C, 0x900213: 0x2D}
    assert _failure_type(dtcs, "B1001") == "1A"
    assert _failure_type(dtcs, "B1003") == "none"
    assert _failure_type({0x90011A: 0x2D, 0x900113: 0x2D}, "B1001") == "13,1A"


def test_parameter_sets_become_cases() -> None:
    module = module_from_table(
        {
            "module": "m",
            "tests": [
                {
                    "id": "T",
                    "title": "wait {ms} ms",
                    "parameters": [{"ms": 10}, {"ms": 20}],
                    "steps": [{"do": "wait", "ms": "{ms}"}],
                },
                {"id": "U", "title": "single", "steps": [{"do": "wait", "ms": 1}]},
            ],
        }
    )
    assert [(case.case_id, case.title) for case in module.cases] == [
        ("T[1]", "wait 10 ms"),
        ("T[2]", "wait 20 ms"),
        ("U", "single"),
    ]
    result = module.run()
    # Steps that only wait record nothing, so the cases end inconclusive.
    assert {case.verdict for case in result.cases} == {Verdict.INCONCLUSIVE}
    assert result.cases[1].end_us - result.cases[1].start_us == 20_000


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ({}, "'tests' list"),
        ({"tests": [{"title": "x", "steps": []}]}, "missing 'id'"),
        ({"tests": [{"id": "A", "title": "x", "steps": []}]}, "non-empty"),
        ({"tests": [{"id": "A", "title": "x", "steps": [{"do": "fly"}]}]}, "unknown action 'fly'"),
        ({"tests": [{"id": "A", "title": "x", "steps": ["wait"]}]}, "must be an object"),
        (
            {
                "tests": [
                    {"id": "A", "title": "x", "steps": [{"do": "wait", "ms": 1}], "parameters": [1]}
                ]
            },
            "list of objects",
        ),
    ],
)
def test_invalid_tables_name_the_problem(table: dict[str, object], message: str) -> None:
    with pytest.raises(TestTableError, match=message):
        module_from_table(table)


def test_invalid_json_reports_the_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{\n  "tests": [\n', encoding="utf-8")
    with pytest.raises(TestTableError, match="line"):
        load_test_table(path)


def test_shipped_table_is_valid_and_uses_known_actions() -> None:
    module = load_test_table(TABLE)
    assert len(module.cases) == 11
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    used = {step["do"] for test in table["tests"] for step in test["steps"]}
    assert used <= set(ACTIONS)
    assert all(case.requirements for case in module.cases)


def test_a_failing_table_step_fails_the_case() -> None:
    module = module_from_table(
        {
            "tests": [
                {
                    "id": "F",
                    "title": "wrong expectation",
                    "steps": [
                        {"do": "switch_on"},
                        {"do": "check_lamp", "on": True},
                        {"do": "scpi", "address": "PSU", "command": "OUTP?", "expect": "0"},
                    ],
                }
            ]
        }
    )
    case = module.run().cases[0]
    assert case.verdict is Verdict.FAIL
    assert [step.verdict for step in case.steps] == [Verdict.FAIL, Verdict.FAIL]
