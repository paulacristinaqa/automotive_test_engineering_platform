from unittest.mock import patch

import pytest

from tools.run_dashboard_proxy_acceptance import target, verify_replicas, verify_upstream


def test_alternating_replica_schedule_includes_both_denials() -> None:
    assert target(29, True) == (18801, "172.30.241.20:8000")
    assert target(30, True) == (18802, "172.30.241.21:8000")
    assert target(31, True) == target(29, True)
    assert target(32, True) == target(30, True)


def test_single_proxy_schedule_is_unchanged() -> None:
    assert target(1, False) == target(32, False) == (18800, None)
    verify_upstream(None, None)


@pytest.mark.parametrize("actual", [None, "172.30.241.21:8000", "spoofed"])
def test_missing_or_wrong_replica_evidence_fails(actual: str | None) -> None:
    with pytest.raises(RuntimeError):
        verify_upstream(actual, "172.30.241.20:8000")


def test_correct_replica_evidence_passes() -> None:
    verify_upstream("172.30.241.20:8000", "172.30.241.20:8000")


def test_same_process_cannot_satisfy_independent_replica_gate() -> None:
    record = '{"id":"same","pid":100,"memory":536870912,"cpu":500000000,"pids":64}'
    with patch(
        "tools.run_dashboard_proxy_acceptance.command", side_effect=["a", record, "b", record]
    ):
        with pytest.raises(RuntimeError, match="independent"):
            verify_replicas("fixture")


def test_unbounded_replica_fails() -> None:
    record = '{"id":"a","pid":100,"memory":0,"cpu":0,"pids":64}'
    with patch("tools.run_dashboard_proxy_acceptance.command", side_effect=["a", record]):
        with pytest.raises(RuntimeError, match="resource bounds"):
            verify_replicas("fixture")
