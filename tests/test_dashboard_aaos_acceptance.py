import sys
from collections.abc import Callable
from functools import partial

import pytest

from tools.run_dashboard_aaos_acceptance import run_instrumentation

CHECKPOINT = "INSTRUMENTATION_STATUS: atep_checkpoint=revocation-ready"
EXPIRY = "INSTRUMENTATION_STATUS: atep_checkpoint=local-expired"
SERVER_EXPIRY = "INSTRUMENTATION_STATUS: atep_checkpoint=server-expired"
INACTIVE = "INSTRUMENTATION_STATUS: atep_checkpoint=inactive-ready"


@pytest.mark.parametrize("missing", [None, 0, 1, 2, 3])
@pytest.mark.parametrize(
    "scenario,terminal", [("retry-expiry", "expired"), ("retry-exhaustion", "stopped")]
)
def test_retry_checkpoints_require_every_phase(
    missing: int | None, scenario: str, terminal: str
) -> None:
    names = [
        f"{scenario}-live",
        f"{scenario}-waiting",
        f"{scenario}-{terminal}",
        f"{scenario}-terminal",
    ]
    source = ";".join(
        f"print('INSTRUMENTATION_STATUS: atep_checkpoint={name}')"
        for index, name in enumerate(names)
        if index != missing
    )
    seen: list[str] = []
    checkpoints: list[tuple[str, Callable[[], None]]] = [
        (name, partial(seen.append, name)) for name in names
    ]
    if missing is None:
        run_instrumentation(command(source), lambda: None, checkpoints=checkpoints)
        assert seen == names
    else:
        with pytest.raises(RuntimeError, match="checkpoint"):
            run_instrumentation(command(source), lambda: None, checkpoints=checkpoints)
        assert seen == names[:missing]


def command(source: str) -> list[str]:
    return [sys.executable, "-u", "-c", source]


@pytest.mark.parametrize("missing", [None, 0, 1, 2])
def test_completion_requires_all_checkpoints(missing: int | None) -> None:
    names = ["completion-live", "completion-complete", "completion-terminal"]
    source = ";".join(
        f"print('INSTRUMENTATION_STATUS: atep_checkpoint={name}')"
        for index, name in enumerate(names)
        if index != missing
    )
    seen: list[str] = []
    checkpoints: list[tuple[str, Callable[[], None]]] = [
        (name, partial(seen.append, name)) for name in names
    ]
    if missing is None:
        run_instrumentation(command(source), lambda: None, checkpoints=checkpoints)
        assert seen == names
    else:
        with pytest.raises(RuntimeError, match="checkpoint"):
            run_instrumentation(command(source), lambda: None, checkpoints=checkpoints)
        assert seen == names[:missing]


def test_custom_checkpoints_preserve_order() -> None:
    calls: list[str] = []
    run_instrumentation(
        command(
            "print('INSTRUMENTATION_STATUS: atep_checkpoint=first'); "
            "print('INSTRUMENTATION_STATUS: atep_checkpoint=second')"
        ),
        lambda: None,
        checkpoints=[
            ("first", lambda: calls.append("first")),
            ("second", lambda: calls.append("second")),
        ],
    )
    assert calls == ["first", "second"]


@pytest.mark.parametrize(
    "names", [[], ["second"], ["first", "first"], ["first", "second", "third"]]
)
def test_invalid_custom_checkpoint_sequence_fails(names: list[str]) -> None:
    source = (
        ";".join(f"print('INSTRUMENTATION_STATUS: atep_checkpoint={name}')" for name in names)
        or "pass"
    )
    with pytest.raises(RuntimeError, match="checkpoint"):
        run_instrumentation(
            command(source),
            lambda: None,
            checkpoints=[("first", lambda: None), ("second", lambda: None)],
        )


def test_exact_checkpoint_invokes_revocation_once() -> None:
    calls: list[bool] = []
    output = run_instrumentation(
        command(f"print({CHECKPOINT!r}); print('INSTRUMENTATION_CODE: -1')"),
        lambda: calls.append(True),
    )
    assert calls == [True]
    assert "INSTRUMENTATION_CODE: -1" in output


def test_missing_checkpoint_cannot_pass() -> None:
    calls: list[bool] = []
    with pytest.raises(RuntimeError, match="checkpoint failed"):
        run_instrumentation(
            command(f"print('prefix ' + {CHECKPOINT!r})"), lambda: calls.append(True)
        )
    assert not calls


def test_duplicate_checkpoint_cannot_repeat_mutation() -> None:
    calls: list[bool] = []
    with pytest.raises(RuntimeError, match="Duplicate"):
        run_instrumentation(
            command(f"print({CHECKPOINT!r}); print({CHECKPOINT!r})"),
            lambda: calls.append(True),
        )
    assert calls == [True]


def test_timeout_is_bounded_and_does_not_echo_child_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(RuntimeError, match="deadline") as error:
        run_instrumentation(
            command("import time; print('private-fixture-value'); time.sleep(10)"),
            lambda: None,
            timeout_seconds=0.2,
        )
    assert "private-fixture-value" not in str(error.value)
    assert capsys.readouterr().out == ""


def test_output_is_bounded() -> None:
    with pytest.raises(RuntimeError, match="output limit"):
        run_instrumentation(command("print('x' * 70000)"), lambda: None)


def test_failed_revocation_terminates_instrumentation() -> None:
    def fail() -> None:
        raise RuntimeError("fixture removal failed")

    with pytest.raises(RuntimeError, match="fixture removal failed"):
        run_instrumentation(command(f"import time; print({CHECKPOINT!r}); time.sleep(10)"), fail)


def test_failed_child_cannot_pass() -> None:
    with pytest.raises(RuntimeError, match="checkpoint failed"):
        run_instrumentation(
            command(f"import sys; print({CHECKPOINT!r}); sys.exit(1)"), lambda: None
        )


def test_expiry_is_verified_before_revocation() -> None:
    calls: list[str] = []
    run_instrumentation(
        command(f"print({EXPIRY!r}); print({CHECKPOINT!r})"),
        lambda: calls.append("revoke"),
        verify_local_expiry=lambda: calls.append("expiry"),
    )
    assert calls == ["expiry", "revoke"]


def test_missing_expiry_prevents_role_mutation() -> None:
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="expiry checkpoint missing"):
        run_instrumentation(
            command(f"print({CHECKPOINT!r})"),
            lambda: calls.append("revoke"),
            verify_local_expiry=lambda: calls.append("expiry"),
        )
    assert not calls


def test_duplicate_expiry_cannot_repeat_probe() -> None:
    calls: list[str] = []
    with pytest.raises(RuntimeError, match="Unexpected AAOS expiry"):
        run_instrumentation(
            command(f"print({EXPIRY!r}); print({EXPIRY!r}); print({CHECKPOINT!r})"),
            lambda: calls.append("revoke"),
            verify_local_expiry=lambda: calls.append("expiry"),
        )
    assert calls == ["expiry"]


def test_failed_server_probe_prevents_revocation() -> None:
    def reject() -> None:
        raise RuntimeError("server token was not valid")

    calls: list[bool] = []
    with pytest.raises(RuntimeError, match="server token was not valid"):
        run_instrumentation(
            command(f"print({EXPIRY!r}); print({CHECKPOINT!r})"),
            lambda: calls.append(True),
            verify_local_expiry=reject,
        )
    assert not calls


def test_server_expiry_checkpoint_is_required_and_ordered() -> None:
    calls: list[str] = []
    run_instrumentation(
        command(f"print({CHECKPOINT!r}); print({SERVER_EXPIRY!r})"),
        lambda: calls.append("revoke"),
        verify_server_expiry=lambda: calls.append("expired"),
    )
    assert calls == ["revoke", "expired"]


def test_missing_server_expiry_cannot_pass() -> None:
    with pytest.raises(RuntimeError, match="server expiry checkpoint missing"):
        run_instrumentation(
            command(f"print({CHECKPOINT!r})"),
            lambda: None,
            verify_server_expiry=lambda: None,
        )


@pytest.mark.parametrize("duplicate", [False, True])
def test_server_expiry_rejects_early_or_duplicate_checkpoint(duplicate: bool) -> None:
    source = f"print({CHECKPOINT!r}); print({SERVER_EXPIRY!r}); " if duplicate else ""
    source += f"print({SERVER_EXPIRY!r})"
    with pytest.raises(RuntimeError, match="Unexpected AAOS server expiry"):
        run_instrumentation(command(source), lambda: None, verify_server_expiry=lambda: None)


def test_server_expiry_probe_failure_cannot_pass() -> None:
    def reject() -> None:
        raise RuntimeError("JWT still valid")

    with pytest.raises(RuntimeError, match="JWT still valid"):
        run_instrumentation(
            command(f"print({CHECKPOINT!r}); print({SERVER_EXPIRY!r})"),
            lambda: None,
            verify_server_expiry=reject,
        )


def test_deactivation_runs_once_after_live_checkpoint() -> None:
    calls: list[str] = []
    run_instrumentation(
        command(f"print({CHECKPOINT!r}); print({INACTIVE!r}); print({SERVER_EXPIRY!r})"),
        lambda: calls.append("revoke"),
        deactivate=lambda: calls.append("disable"),
        verify_server_expiry=lambda: calls.append("expiry"),
    )
    assert calls == ["revoke", "disable", "expiry"]


@pytest.mark.parametrize("duplicate", [False, True])
def test_early_or_duplicate_deactivation_is_rejected(duplicate: bool) -> None:
    calls: list[bool] = []
    source = f"print({CHECKPOINT!r}); print({INACTIVE!r}); " if duplicate else ""
    with pytest.raises(RuntimeError, match="Unexpected AAOS deactivation"):
        run_instrumentation(
            command(source + f"print({INACTIVE!r})"),
            lambda: None,
            deactivate=lambda: calls.append(True),
        )
    assert calls == ([True] if duplicate else [])


def test_missing_deactivation_cannot_pass() -> None:
    with pytest.raises(RuntimeError, match="deactivation checkpoint missing"):
        run_instrumentation(
            command(f"print({CHECKPOINT!r})"),
            lambda: None,
            deactivate=lambda: None,
        )


def test_missing_deactivation_prevents_server_expiry_probe() -> None:
    calls: list[bool] = []
    with pytest.raises(RuntimeError, match="deactivation checkpoint missing"):
        run_instrumentation(
            command(f"print({CHECKPOINT!r}); print({SERVER_EXPIRY!r})"),
            lambda: None,
            deactivate=lambda: None,
            verify_server_expiry=lambda: calls.append(True),
        )
    assert not calls


def test_failed_deactivation_cannot_pass() -> None:
    def reject() -> None:
        raise RuntimeError("fixture deactivation failed")

    with pytest.raises(RuntimeError, match="fixture deactivation failed"):
        run_instrumentation(
            command(f"print({CHECKPOINT!r}); print({INACTIVE!r})"),
            lambda: None,
            deactivate=reject,
        )
