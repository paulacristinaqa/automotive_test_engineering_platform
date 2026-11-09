"""Opt-in AAOS network fault scenario against the disposable local API only."""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from tools.aaos_network_proxy import LoopbackFaultProxy
from tools.run_dashboard_aaos_acceptance import run_instrumentation


def validate_retry_history(count: int, times: tuple[float, ...], cut_at: float) -> None:
    if count != 6 or len(times) != 6:
        raise RuntimeError("Expected initial connection and exactly five retries")
    starts = (cut_at, *times[1:-1])
    for previous, current, delay in zip(starts, times[1:], (30, 60, 120, 120, 120), strict=True):
        if current - previous < delay - 1:
            raise RuntimeError("Retry backoff was shorter than policy")


def main() -> None:
    expiry = sys.argv[1:] == ["--expiry-during-retry"]
    exhaustion = sys.argv[1:] == ["--retry-exhaustion"]
    completion = sys.argv[1:] == ["--normal-completion"]
    if sys.argv[1:] and not (expiry or exhaustion or completion):
        raise RuntimeError("Unknown scenario")
    if os.environ.get("ATEP_INTEGRATION_API_URL") != "http://localhost:18000":
        raise RuntimeError("Disposable runner required")
    adb = Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/platform-tools/adb.exe"
    prefix = [str(adb), "-s", "emulator-5554"]

    def run(*args: str) -> str:
        result = subprocess.run([*prefix, *args], capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError("AAOS command failed; raw output suppressed")
        return result.stdout

    if run("shell", "getprop", "ro.kernel.qemu").strip() != "1":
        raise RuntimeError("Emulator required")
    user = run("shell", "am", "get-current-user").strip()
    if not user.isdigit():
        raise RuntimeError("Invalid test user")
    apk_root = Path("C:/projetos/CarSystemUI_android/showcase/app/build/outputs/apk")
    print("AAOS network: installing test APKs", flush=True)
    run("install", "-r", str(apk_root / "debug/app-debug.apk"))
    run("install", "-r", str(apk_root / "androidTest/debug/app-debug-androidTest.apk"))

    def login(email: str, password: str) -> str:
        request = urllib.request.Request(
            "http://localhost:18000/api/v1/auth/token",
            data=urllib.parse.urlencode({"username": email, "password": password}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            pair = json.load(response)
            if completion and pair["expires_in"] != 600:
                raise RuntimeError("Completion requires the isolated ten-minute fixture")
            return str(pair["access_token"])

    admin = login(
        os.environ["ATEP_INTEGRATION_ADMIN_EMAIL"], os.environ["ATEP_INTEGRATION_ADMIN_PASSWORD"]
    )
    print("AAOS network: creating disposable reader", flush=True)

    def api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://localhost:18000{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {admin}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return cast(dict[str, Any], json.load(response))

    email = f"aaos-network-{uuid4().hex}@example.com"
    password = f"Aaos-{uuid4().hex}!"
    account = api(
        "POST",
        "/api/v1/users",
        {"email": email, "display_name": "AAOS network fixture", "password": password},
    )
    role = api(
        "POST",
        "/api/v1/roles",
        {
            "name": f"aaos-network-{uuid4().hex[:12]}",
            "description": "Disposable network fixture",
            "permissions": ["dashboard:read"],
        },
    )
    api("PUT", f"/api/v1/users/{account['id']}/roles/{role['id']}")
    issued_at = time.monotonic()
    token = login(email, password)
    print("AAOS network: reader ready; starting instrumentation", flush=True)
    if completion:
        run("shell", "rm", "-f", "/data/local/tmp/atep-aaos-completion-failure.png")
    try:
        with LoopbackFaultProxy() as proxy:
            paused_at = 0.0
            cut_at = 0.0

            def pause() -> None:
                nonlocal paused_at
                if proxy.accepted != 1:
                    raise RuntimeError("Unexpected initial connection count")
                proxy.pause()
                paused_at = time.monotonic()
                print("AAOS network: LIVE confirmed; traffic paused", flush=True)

            def cut() -> None:
                nonlocal cut_at
                if time.monotonic() - paused_at < 29:
                    raise RuntimeError("Staleness observed too early")
                proxy.cut()
                cut_at = time.monotonic()
                print("AAOS network: stale evidence confirmed; connection interrupted", flush=True)

            def restore() -> None:
                if proxy.accepted != 1:
                    raise RuntimeError("Client retried before recovery checkpoint")
                proxy.restore()
                print("AAOS network: backoff confirmed; route restored", flush=True)

            def recovered() -> None:
                if proxy.accepted != 2 or time.monotonic() - cut_at < 29:
                    raise RuntimeError("Reconnect count or minimum backoff violated")
                print("AAOS network: fresh LIVE evidence after one delayed reconnect", flush=True)

            def cut_live() -> None:
                nonlocal cut_at
                if proxy.accepted != 1:
                    raise RuntimeError("Unexpected initial connection count")
                proxy.cut()
                cut_at = time.monotonic()
                print("AAOS retry expiry: LIVE confirmed; connection interrupted", flush=True)

            def expired() -> None:
                if proxy.accepted != 1:
                    raise RuntimeError("Unexpected connection before local expiry")
                probe = urllib.request.Request(
                    "http://localhost:18000/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with urllib.request.urlopen(probe, timeout=10) as response:
                    reader = json.load(response)
                    if not reader["is_active"] or "dashboard:read" not in reader["permissions"]:
                        raise RuntimeError("Reader is not still authorized")
                proxy.restore()
                print("AAOS retry expiry: server still accepts JWT; route restored", flush=True)

            def terminal() -> None:
                if proxy.accepted != 1:
                    raise RuntimeError("Expired client restarted automatically")
                print("AAOS retry expiry: no reconnect after route recovery", flush=True)

            def exhausted() -> None:
                validate_retry_history(proxy.accepted, proxy.accepted_at, cut_at)
                proxy.restore()
                print("AAOS exhaustion: five delayed retries; STOPPED; route restored", flush=True)

            def exhausted_terminal() -> None:
                if proxy.accepted != 6:
                    raise RuntimeError("Exhausted client restarted automatically")
                print("AAOS exhaustion: no restart beyond maximum backoff", flush=True)

            def completion_live() -> None:
                if proxy.accepted != 1 or time.monotonic() - issued_at >= 60:
                    raise RuntimeError("Initial LIVE did not reserve sufficient JWT lifetime")
                print("AAOS completion: LIVE confirmed with reserved JWT lifetime", flush=True)

            def completed() -> None:
                if proxy.accepted != 1 or time.monotonic() - proxy.accepted_at[0] < 269:
                    raise RuntimeError("Normal completion reconnected unexpectedly")
                print("AAOS completion: ten snapshots completed normally", flush=True)

            def completion_terminal() -> None:
                if proxy.accepted != 1:
                    raise RuntimeError("Completed client restarted automatically")
                print(
                    "AAOS completion: retained terminal evidence; no automatic restart", flush=True
                )

            output = run_instrumentation(
                [
                    *prefix,
                    "shell",
                    "am",
                    "instrument",
                    "--user",
                    user,
                    "-w",
                    "-e",
                    "scenario",
                    "normal-completion"
                    if completion
                    else "retry-exhaustion"
                    if exhaustion
                    else "retry-expiry"
                    if expiry
                    else "network",
                    "-e",
                    "base_url",
                    "http://10.0.2.2:18001",
                    "-e",
                    "access_token",
                    token,
                    "com.example.carsystemui.showcase.test/com.example.carsystemui.showcase.dashboard.DashboardAcceptance",
                ],
                lambda: None,
                timeout_seconds=720 if exhaustion else 360 if completion else 180,
                checkpoints=[
                    ("completion-live", completion_live),
                    ("completion-complete", completed),
                    ("completion-terminal", completion_terminal),
                ]
                if completion
                else [
                    ("retry-exhaustion-live", cut_live),
                    ("retry-exhaustion-waiting", lambda: None),
                    ("retry-exhaustion-stopped", exhausted),
                    ("retry-exhaustion-terminal", exhausted_terminal),
                ]
                if exhaustion
                else [
                    ("retry-expiry-live", cut_live),
                    ("retry-expiry-waiting", lambda: None),
                    ("retry-expiry-expired", expired),
                    ("retry-expiry-terminal", terminal),
                ]
                if expiry
                else [
                    ("network-live", pause),
                    ("network-stale", cut),
                    ("network-retrying", restore),
                    ("network-restored", recovered),
                ],
            )
            if "atep_result=PASS:" not in output or "INSTRUMENTATION_CODE: -1" not in output:
                raise RuntimeError("AAOS network assertions failed")
            Path("dr-evidence").mkdir(exist_ok=True)
            for name in (
                ("completed",)
                if completion
                else ("exhausted",)
                if exhaustion
                else ("retry-expired",)
                if expiry
                else ("stale", "reconnected")
            ):
                run(
                    "pull",
                    f"/data/local/tmp/atep-aaos-network-{name}.png",
                    f"dr-evidence/dashboard-aaos-network-{name}.png",
                )
            print(
                "PASS: AAOS normal completion"
                if completion
                else "PASS: AAOS retry exhaustion"
                if exhaustion
                else "PASS: AAOS retry expiry"
                if expiry
                else "PASS: AAOS stalled transport, stale retention, backoff and fresh reconnect"
            )
    finally:
        if completion:
            Path("dr-evidence").mkdir(exist_ok=True)
            try:
                run(
                    "pull",
                    "/data/local/tmp/atep-aaos-completion-failure.png",
                    "dr-evidence/dashboard-aaos-completion-failure.png",
                )
                print("AAOS completion: failure screenshot retained locally", flush=True)
            except RuntimeError:
                pass
        token = ""
        run("shell", "am", "force-stop", "--user", user, "com.example.carsystemui.showcase")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("AAOS network acceptance failed; credentials and raw output suppressed")
        raise SystemExit(1) from None
