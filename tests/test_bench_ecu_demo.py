import json
from pathlib import Path
from uuid import uuid4

from atep.bench.bus import BenchBusConfig
from tools.run_ecu_communication_demo import DIAGNOSTIC_STEPS, main, run_demo


def test_simulated_demo_passes_every_step_and_writes_traces(tmp_path: Path) -> None:
    report = run_demo(tmp_path)
    assert report.passed, [step.name for step in report.steps if not step.passed]
    assert len(report.steps) == len(DIAGNOSTIC_STEPS)
    assert report.e2e_passed and report.supervision_passed
    names = sorted(path.name for path in tmp_path.iterdir())
    assert names == ["diagnostics.asc", "diagnostics.blf", "e2e.asc", "e2e.blf", "report.json"]
    summary = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    pending = next(step for step in summary["steps"] if "pending" in step["name"])
    assert pending["pending_count"] >= 1


def test_simulated_demo_is_reproducible(tmp_path: Path) -> None:
    first = run_demo(tmp_path / "a")
    second = run_demo(tmp_path / "b")
    assert first.files == second.files


def test_demo_runs_the_diagnostic_session_on_a_python_can_bus(tmp_path: Path) -> None:
    report = run_demo(tmp_path, bus=BenchBusConfig(channel=f"atep-ecd-{uuid4()}"))
    assert report.mode == "bus"
    assert report.passed, [step.name for step in report.steps if not step.passed]
    # The S3 step needs a 6 s wait and only runs on the simulated link.
    assert len(report.steps) == len(DIAGNOSTIC_STEPS) - 1


def test_cli_exit_code(tmp_path: Path) -> None:
    assert main(["--output", str(tmp_path)]) == 0
