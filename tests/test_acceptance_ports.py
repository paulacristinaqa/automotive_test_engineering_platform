import pytest

from tools.acceptance_ports import PROXY_HTTP, PROXY_REPLICA_A, PROXY_REPLICA_B, PROXY_TLS, port
from tools.run_dashboard_proxy_acceptance import target


def test_defaults_are_the_documented_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable, _ in (PROXY_HTTP, PROXY_REPLICA_A, PROXY_REPLICA_B, PROXY_TLS):
        monkeypatch.delenv(variable, raising=False)
    assert [port(item) for item in (PROXY_HTTP, PROXY_REPLICA_A, PROXY_REPLICA_B, PROXY_TLS)] == [
        18800,
        18801,
        18802,
        18443,
    ]


def test_ports_move_with_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATEP_ACCEPTANCE_PROXY_PORT", "18900")
    monkeypatch.setenv("ATEP_ACCEPTANCE_REPLICA_A_PORT", "18901")
    monkeypatch.setenv("ATEP_ACCEPTANCE_REPLICA_B_PORT", " 18902 ")
    assert target(1, False) == (18900, None)
    assert target(29, True) == (18901, "172.30.241.20:8000")
    assert target(30, True) == (18902, "172.30.241.21:8000")


@pytest.mark.parametrize("value", ["80", "70000", "abc", "-1"])
def test_invalid_ports_are_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ATEP_ACCEPTANCE_TLS_PORT", value)
    with pytest.raises(ValueError, match="ATEP_ACCEPTANCE_TLS_PORT"):
        port(PROXY_TLS)
