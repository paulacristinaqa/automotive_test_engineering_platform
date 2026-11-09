"""Opt-in real AAOS smoke against the disposable integration stack only."""

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from queue import Empty, Full, Queue
from uuid import uuid4


def run_instrumentation(
    command: list[str],
    revoke: Callable[[], None],
    timeout_seconds: float = 180,
    *,
    verify_local_expiry: Callable[[], None] | None = None,
    verify_server_expiry: Callable[[], None] | None = None,
    deactivate: Callable[[], None] | None = None,
    checkpoints: list[tuple[str, Callable[[], None]]] | None = None,
) -> str:
    """React only to an exact test checkpoint; never print child output or argv."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    output: Queue[str | None] = Queue(maxsize=64)
    stopped = threading.Event()

    def enqueue(value: str | None) -> None:
        while not stopped.is_set():
            try:
                output.put(value, timeout=0.1)
                return
            except Full:
                continue

    def read_output() -> None:
        assert process.stdout is not None
        try:
            while not stopped.is_set():
                chunk = process.stdout.readline(4096)
                if not chunk:
                    break
                enqueue(chunk)
        finally:
            enqueue(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    chunks: list[str] = []
    size = 0
    revoked = False
    expiry_verified = False
    server_expiry_verified = False
    deactivated = False
    checkpoint_index = 0
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("AAOS instrumentation deadline exceeded")
            try:
                chunk = output.get(timeout=min(0.5, remaining))
            except Empty:
                continue
            if chunk is None:
                break
            size += len(chunk)
            if size > 65_536:
                raise RuntimeError("AAOS instrumentation output limit exceeded")
            chunks.append(chunk)
            if checkpoints is not None:
                for phase in (
                    "network-form",
                    "network-stale",
                    "network-retrying",
                    "network-restored",
                    "retry-expiry-form",
                    "retry-expiry-waiting",
                    "retry-expiry-expired",
                    "retry-expiry-terminal",
                    "retry-exhaustion-form",
                    "retry-exhaustion-waiting",
                    "retry-exhaustion-stopped",
                    "retry-exhaustion-terminal",
                    "completion-form",
                    "completion-complete",
                    "completion-terminal",
                    "completion-duration",
                    "completion-stale",
                    "completion-preview",
                    "completion-preview-sequence",
                    "completion-preview-text",
                    "completion-token",
                ):
                    if chunk.strip() == f"INSTRUMENTATION_RESULT: atep_phase={phase}":
                        print(f"AAOS assertion failed in phase: {phase}", flush=True)
            if checkpoints is not None and chunk.startswith(
                "INSTRUMENTATION_STATUS: atep_checkpoint="
            ):
                if checkpoint_index >= len(checkpoints):
                    raise RuntimeError("Unexpected extra AAOS checkpoint")
                name, callback = checkpoints[checkpoint_index]
                if chunk.strip() != f"INSTRUMENTATION_STATUS: atep_checkpoint={name}":
                    raise RuntimeError("Unexpected AAOS checkpoint order")
                callback()
                checkpoint_index += 1
                continue
            if chunk.strip() == "INSTRUMENTATION_STATUS: atep_checkpoint=inactive-ready":
                if deactivated or deactivate is None or not revoked or server_expiry_verified:
                    raise RuntimeError("Unexpected AAOS deactivation checkpoint")
                deactivate()
                deactivated = True
            if chunk.strip() == "INSTRUMENTATION_STATUS: atep_checkpoint=server-expired":
                if deactivate is not None and not deactivated:
                    raise RuntimeError("AAOS deactivation checkpoint missing before server expiry")
                if server_expiry_verified or verify_server_expiry is None or not revoked:
                    raise RuntimeError("Unexpected AAOS server expiry checkpoint")
                verify_server_expiry()
                server_expiry_verified = True
            if chunk.strip() == "INSTRUMENTATION_STATUS: atep_checkpoint=local-expired":
                if expiry_verified or verify_local_expiry is None or revoked:
                    raise RuntimeError("Unexpected AAOS expiry checkpoint")
                verify_local_expiry()
                expiry_verified = True
            if chunk.strip() == "INSTRUMENTATION_STATUS: atep_checkpoint=revocation-ready":
                if verify_local_expiry is not None and not expiry_verified:
                    raise RuntimeError("AAOS expiry checkpoint missing before revocation")
                if revoked:
                    raise RuntimeError("Duplicate AAOS revocation checkpoint")
                revoke()
                revoked = True
        if checkpoints is not None:
            if checkpoint_index != len(checkpoints) or not checkpoints:
                raise RuntimeError("AAOS checkpoint sequence incomplete")
        if process.wait(timeout=max(0.1, deadline - time.monotonic())) != 0 or (
            checkpoints is None and not revoked
        ):
            raise RuntimeError("AAOS instrumentation or revocation checkpoint failed")
        if verify_server_expiry is not None and not server_expiry_verified:
            raise RuntimeError("AAOS server expiry checkpoint missing")
        if deactivate is not None and not deactivated:
            raise RuntimeError("AAOS deactivation checkpoint missing")
        return "".join(chunks)
    finally:
        stopped.set()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        reader.join(timeout=2)
        process.stdout.close()


def main() -> None:
    if os.environ.get("ATEP_INTEGRATION_API_URL") != "http://localhost:18000":
        raise RuntimeError("Disposable runner required")
    adb = Path(os.environ["LOCALAPPDATA"]) / "Android/Sdk/platform-tools/adb.exe"
    prefix = [str(adb), "-s", "emulator-5554"]

    def run(*args: str) -> str:
        result = subprocess.run([*prefix, *args], capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError("AAOS command failed; credential output suppressed")
        return result.stdout

    if run("shell", "getprop", "ro.kernel.qemu").strip() != "1":
        raise RuntimeError("Only an emulator is allowed")
    user = run("shell", "am", "get-current-user").strip()
    if not user.isdigit():
        raise RuntimeError("Invalid Android test user")
    apk_root = Path("C:/projetos/CarSystemUI_android/showcase/app/build/outputs/apk")
    print("AAOS stage: installing test APKs", flush=True)
    run("install", "-r", str(apk_root / "debug/app-debug.apk"))
    run("install", "-r", str(apk_root / "androidTest/debug/app-debug-androidTest.apk"))
    body = urllib.parse.urlencode(
        {
            "username": os.environ["ATEP_INTEGRATION_ADMIN_EMAIL"],
            "password": os.environ["ATEP_INTEGRATION_ADMIN_PASSWORD"],
        }
    ).encode()
    request = urllib.request.Request(
        "http://localhost:18000/api/v1/auth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        token = json.load(response)["access_token"]
    try:
        # A new account without roles exists only in the disposable fixture.
        email = f"aaos-denied-{uuid4().hex}@example.com"
        password = f"Aaos-{uuid4().hex}!"
        create_request = urllib.request.Request(
            "http://localhost:18000/api/v1/users",
            data=json.dumps(
                {"email": email, "display_name": "AAOS denied fixture", "password": password}
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(create_request, timeout=10) as response:
            if response.status != 201:
                raise RuntimeError("Denied fixture creation failed")
        denied_request = urllib.request.Request(
            "http://localhost:18000/api/v1/auth/token",
            data=urllib.parse.urlencode({"username": email, "password": password}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(denied_request, timeout=10) as response:
            denied_token = json.load(response)["access_token"]

        # A separate account starts with one narrowly scoped, removable role.
        role_request = urllib.request.Request(
            "http://localhost:18000/api/v1/roles",
            data=json.dumps(
                {
                    "name": f"aaos-dashboard-{uuid4().hex[:12]}",
                    "description": "Disposable AAOS revocation fixture",
                    "permissions": ["dashboard:read"],
                }
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(role_request, timeout=10) as response:
            role_id = json.load(response)["id"]
        revocable_email = f"aaos-revoke-{uuid4().hex}@example.com"
        revocable_request = urllib.request.Request(
            "http://localhost:18000/api/v1/users",
            data=json.dumps(
                {
                    "email": revocable_email,
                    "display_name": "AAOS revocation fixture",
                    "password": password,
                }
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(revocable_request, timeout=10) as response:
            revocable_id = json.load(response)["id"]
        role_url = f"http://localhost:18000/api/v1/users/{revocable_id}/roles/{role_id}"
        assignment = urllib.request.Request(
            role_url, method="PUT", headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(assignment, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("AAOS fixture role assignment failed")
        login_request = urllib.request.Request(
            "http://localhost:18000/api/v1/auth/token",
            data=urllib.parse.urlencode(
                {
                    "username": revocable_email,
                    "password": password,
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(login_request, timeout=10) as response:
            revocable_token = json.load(response)["access_token"]

        server_email = f"aaos-expiry-{uuid4().hex}@example.com"
        server_user_request = urllib.request.Request(
            "http://localhost:18000/api/v1/users",
            data=json.dumps(
                {
                    "email": server_email,
                    "display_name": "AAOS server expiry fixture",
                    "password": password,
                }
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(server_user_request, timeout=10) as response:
            server_user_id = json.load(response)["id"]
        server_assignment = urllib.request.Request(
            f"http://localhost:18000/api/v1/users/{server_user_id}/roles/{role_id}",
            method="PUT",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(server_assignment, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("Server expiry fixture assignment failed")
        server_login = urllib.request.Request(
            "http://localhost:18000/api/v1/auth/token",
            data=urllib.parse.urlencode({"username": server_email, "password": password}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        server_issued_at = time.monotonic()
        with urllib.request.urlopen(server_login, timeout=10) as response:
            server_pair = json.load(response)
        server_token = server_pair["access_token"]
        if server_pair["expires_in"] != 300:
            raise RuntimeError("Server expiry scenario requires the five-minute integration policy")

        inactive_email = f"aaos-inactive-{uuid4().hex}@example.com"
        inactive_request = urllib.request.Request(
            "http://localhost:18000/api/v1/users",
            data=json.dumps(
                {
                    "email": inactive_email,
                    "display_name": "AAOS inactive fixture",
                    "password": password,
                }
            ).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(inactive_request, timeout=10) as response:
            inactive_id = json.load(response)["id"]
        inactive_assignment = urllib.request.Request(
            f"http://localhost:18000/api/v1/users/{inactive_id}/roles/{role_id}",
            method="PUT",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(inactive_assignment, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("Inactive fixture assignment failed")
        inactive_login = urllib.request.Request(
            "http://localhost:18000/api/v1/auth/token",
            data=urllib.parse.urlencode(
                {"username": inactive_email, "password": password}
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        inactive_issued_at = time.monotonic()
        with urllib.request.urlopen(inactive_login, timeout=10) as response:
            inactive_pair = json.load(response)
        inactive_token = inactive_pair["access_token"]
        if inactive_pair["expires_in"] != 300:
            raise RuntimeError("Inactive fixture requires the five-minute integration policy")

        def deactivate_user() -> None:
            # Reserve more than the 65-second device assertion window before JWT expiry.
            if time.monotonic() - inactive_issued_at >= 220:
                raise RuntimeError("Insufficient unexpired JWT window for deactivation")
            disable = urllib.request.Request(
                f"http://localhost:18000/api/v1/users/{inactive_id}/status",
                method="PATCH",
                data=json.dumps({"is_active": False}).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(disable, timeout=10) as response:
                account = json.load(response)
                if account["is_active"] or "dashboard:read" not in account["permissions"]:
                    raise RuntimeError("Inactive fixture status or role changed unexpectedly")
            probe = urllib.request.Request(
                "http://localhost:18000/api/v1/auth/me",
                headers={"Authorization": f"Bearer {inactive_token}"},
            )
            try:
                with urllib.request.urlopen(probe, timeout=10):
                    raise RuntimeError("Inactive user token was accepted")
            except urllib.error.HTTPError as error:
                if error.code != 401 or json.load(error)["error"]["code"] != "invalid_credentials":
                    raise RuntimeError("Unexpected inactive user response") from None
            if time.monotonic() - inactive_issued_at >= 230:
                raise RuntimeError("Deactivation verification exceeded the unexpired window")
            print(
                "AAOS stage: user deactivated after LIVE; role retained; token rejected", flush=True
            )

        def revoke_role() -> None:
            removal = urllib.request.Request(
                role_url, method="DELETE", headers={"Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(removal, timeout=10) as response:
                if response.status != 200 or json.load(response)["roles"]:
                    raise RuntimeError("AAOS fixture role removal failed")
            print("AAOS stage: role removed after device LIVE checkpoint", flush=True)

        def verify_local_expiry() -> None:
            probe = urllib.request.Request(
                "http://localhost:18000/api/v1/auth/me",
                headers={"Authorization": f"Bearer {revocable_token}"},
            )
            with urllib.request.urlopen(probe, timeout=10) as response:
                account = json.load(response)
                if (
                    response.status != 200
                    or not account["is_active"]
                    or "dashboard:read" not in account["permissions"]
                ):
                    raise RuntimeError("Local expiry was not isolated from server authorization")
            print("AAOS stage: local expiry confirmed while server token remains valid", flush=True)

        def verify_server_expiry() -> None:
            if time.monotonic() - server_issued_at < 298:
                raise RuntimeError("Server rejection occurred before expected JWT expiration")
            expired_probe = urllib.request.Request(
                "http://localhost:18000/api/v1/auth/me",
                headers={"Authorization": f"Bearer {server_token}"},
            )
            try:
                with urllib.request.urlopen(expired_probe, timeout=10):
                    raise RuntimeError("Expired server token was accepted")
            except urllib.error.HTTPError as error:
                if error.code != 401 or json.load(error)["error"]["code"] != "invalid_credentials":
                    raise RuntimeError("Unexpected server expiry response") from None
            # Authenticate again: the original administrator token also expired.
            with urllib.request.urlopen(request, timeout=10) as response:
                fresh_admin_token = json.load(response)["access_token"]
            account_probe = urllib.request.Request(
                f"http://localhost:18000/api/v1/users/{server_user_id}",
                headers={"Authorization": f"Bearer {fresh_admin_token}"},
            )
            with urllib.request.urlopen(account_probe, timeout=10) as response:
                account = json.load(response)
                if not account["is_active"] or "dashboard:read" not in account["permissions"]:
                    raise RuntimeError("Server expiry account authorization unexpectedly changed")
            print(
                "AAOS stage: JWT expired; server rejects token; account remains authorized",
                flush=True,
            )

        print("AAOS stage: instrumented scenario", flush=True)
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
                "base_url",
                "http://10.0.2.2:18000",
                "-e",
                "access_token",
                revocable_token,
                "-e",
                "denied_token",
                denied_token,
                "-e",
                "revocable_token",
                revocable_token,
                "-e",
                "server_expiry_token",
                server_token,
                "-e",
                "inactive_token",
                inactive_token,
                "com.example.carsystemui.showcase.test/com.example.carsystemui.showcase.dashboard.DashboardAcceptance",
            ],
            revoke_role,
            timeout_seconds=480,
            verify_local_expiry=verify_local_expiry,
            verify_server_expiry=verify_server_expiry,
            deactivate=deactivate_user,
        )
        if "atep_result=PASS:" not in output or "INSTRUMENTATION_CODE: -1" not in output:
            for control in ("local", "origin", "lifetime", "token", "connect", "status"):
                if f"atep_control=dashboard-{control}\n" in output:
                    print(f"AAOS control: {control}", flush=True)
            for phase in (
                "launch",
                "form",
                "live",
                "token-clear",
                "background",
                "return",
                "stopped",
                "forbidden",
                "revocation-live",
                "revocation-denied",
                "expiry-live",
                "expiry-auth",
                "server-expiry-live",
                "server-expiry-auth",
                "inactive-live",
                "inactive-auth",
            ):
                if f"atep_phase={phase}\n" in output:
                    print(f"AAOS assertion stage: {phase}", flush=True)
            raise RuntimeError("AAOS smoke assertions failed; credential output suppressed")
        Path("dr-evidence").mkdir(exist_ok=True)
        run("pull", "/data/local/tmp/atep-aaos-live.png", "dr-evidence/dashboard-aaos-live.png")
        run(
            "pull",
            "/data/local/tmp/atep-aaos-revoked.png",
            "dr-evidence/dashboard-aaos-revoked.png",
        )
        run(
            "pull",
            "/data/local/tmp/atep-aaos-expired.png",
            "dr-evidence/dashboard-aaos-expired.png",
        )
        run(
            "pull",
            "/data/local/tmp/atep-aaos-server-expired.png",
            "dr-evidence/dashboard-aaos-server-expired.png",
        )
        run(
            "pull",
            "/data/local/tmp/atep-aaos-inactive.png",
            "dr-evidence/dashboard-aaos-inactive.png",
        )
        print("PASS: AAOS live, cleanup, denial, expiry, permission loss and inactive user")
    finally:
        token = ""
        run("shell", "am", "force-stop", "--user", user, "com.example.carsystemui.showcase")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("AAOS acceptance failed; no credentials or raw command output retained")
        raise SystemExit(1) from None
