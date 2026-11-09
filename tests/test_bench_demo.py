import json
from pathlib import Path
from uuid import uuid4

from atep.bench.bus import BenchBusConfig
from tools.run_virtual_bench_demo import main, run_demo


def _config() -> BenchBusConfig:
    return BenchBusConfig(channel=f"atep-demo-{uuid4()}", fd=True, data_bitrate_kbps=2000)


def test_demo_passes_and_writes_vector_files(tmp_path: Path) -> None:
    report = run_demo(tmp_path, config=_config(), duration_ms=200)
    assert report.passed
    assert report.frames_scheduled == report.frames_received == 20 + 10 + 2
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "network.dbc",
        "report.json",
        "trace.asc",
        "trace.blf",
    ]
    summary = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert set(summary["files"]) == {"network.dbc", "trace.asc", "trace.blf"}


def test_demo_files_are_reproducible(tmp_path: Path) -> None:
    first = run_demo(tmp_path / "a", config=_config(), duration_ms=100)
    second = run_demo(tmp_path / "b", config=_config(), duration_ms=100)
    assert first.files == second.files


def test_cli_returns_zero_on_success(tmp_path: Path) -> None:
    code = main(
        ["--output", str(tmp_path), "--channel", f"atep-cli-{uuid4()}", "--duration-ms", "50"]
    )
    assert code == 0
