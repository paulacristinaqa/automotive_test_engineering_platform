import pytest

from tools.run_dashboard_aaos_network_acceptance import validate_retry_history


def test_production_retry_schedule_passes() -> None:
    validate_retry_history(6, (0, 40, 100, 220, 340, 460), 10)


@pytest.mark.parametrize("count", [0, 1, 5, 7])
def test_incorrect_connection_count_fails(count: int) -> None:
    with pytest.raises(RuntimeError, match="exactly five"):
        validate_retry_history(count, (0, 40, 100, 220, 340, 460), 10)


@pytest.mark.parametrize("index", [1, 2, 3, 4, 5])
def test_each_retry_minimum_is_enforced(index: int) -> None:
    times = [0.0, 40.0, 100.0, 220.0, 340.0, 460.0]
    times[index] -= 2
    with pytest.raises(RuntimeError, match="shorter"):
        validate_retry_history(6, tuple(times), 10)


def test_truncated_timestamp_history_fails() -> None:
    with pytest.raises(RuntimeError, match="exactly five"):
        validate_retry_history(6, (0, 40), 10)
