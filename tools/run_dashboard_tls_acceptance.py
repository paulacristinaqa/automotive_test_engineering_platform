"""Disposable TLS acceptance. Never installs trust or disables verification."""

import argparse
import asyncio
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
from pathlib import Path

import httpx
from websockets.asyncio.client import connect

from tools.acceptance_ports import PROXY_HTTP, PROXY_TLS, port

ROOT = Path(__file__).resolve().parents[1]


def command(args: list[str], env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120, check=False
    )
    if result.returncode:
        # Docker output can contain interpolated secrets; do not echo it.
        raise RuntimeError("TLS fixture command failed")
    return result.stdout.strip()


def openssl_executable() -> str:
    openssl = shutil.which("openssl")
    if openssl is None:
        bundled = Path("C:/Program Files/Git/usr/bin/openssl.exe")
        if bundled.is_file():
            openssl = str(bundled)
    if openssl is None:
        raise RuntimeError("OpenSSL executable required (Git for Windows includes it)")
    return openssl


def certificates(directory: Path) -> None:
    openssl = openssl_executable()
    # A one-day self-signed localhost leaf is explicitly trusted only by this process.
    command(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
            "-keyout",
            str(directory / "server.key"),
            "-out",
            str(directory / "server.crt"),
        ]
    )


def trusted_context(certificate: Path) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=str(certificate))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def handshake(context: ssl.SSLContext, hostname: str) -> str | None:
    with socket.create_connection(("127.0.0.1", port(PROXY_TLS)), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname=hostname) as secured:
            return secured.version()


def rejected_certificate(context: ssl.SSLContext, hostname: str) -> None:
    try:
        handshake(context, hostname)
    except ssl.SSLCertVerificationError:
        return
    raise AssertionError("Certificate verification did not reject the connection")


async def acceptance(certificate: Path) -> None:
    context = trusted_context(certificate)
    for attempt in range(20):
        try:
            await asyncio.to_thread(handshake, context, "localhost")
            break
        except (ConnectionRefusedError, ConnectionResetError):
            if attempt == 19:
                raise
            await asyncio.sleep(0.5)
    for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
        version_context = trusted_context(certificate)
        version_context.minimum_version = version
        version_context.maximum_version = version
        assert await asyncio.to_thread(
            handshake, version_context, "localhost"
        ) == version.name.replace("_", ".")
    await asyncio.to_thread(rejected_certificate, ssl.create_default_context(), "localhost")
    await asyncio.to_thread(rejected_certificate, context, "wrong-host.invalid")
    async with httpx.AsyncClient(
        base_url=f"https://localhost:{port(PROXY_TLS)}", verify=context, trust_env=False, timeout=10
    ) as api:
        ready = await api.get("/health/ready")
        assert ready.status_code == 200 and ready.json()["status"] == "ready"
        response = await api.post(
            "/api/v1/auth/token",
            data={
                "username": os.environ["ATEP_INTEGRATION_ADMIN_EMAIL"],
                "password": os.environ["ATEP_INTEGRATION_ADMIN_PASSWORD"],
            },
        )
        response.raise_for_status()
        token = response.json()["access_token"]
    async with connect(
        f"wss://localhost:{port(PROXY_TLS)}/api/v1/dashboard/stream/operations",
        ssl=context,
        proxy=None,
        additional_headers={"Authorization": f"Bearer {token}"},
        open_timeout=5,
        close_timeout=1,
    ) as stream:
        event = json.loads(await asyncio.wait_for(stream.recv(), timeout=10))
        assert event["type"] == "atep.dashboard.snapshot.v1" and event["sequence"] == 1
    print("PASS: TLS 1.2/1.3, verified HTTPS/WSS, untrusted and wrong-host rejection", flush=True)


def main(project: str, *, lifecycle: bool = False) -> None:
    if os.environ.get("ATEP_INTEGRATION_API_URL") != "http://localhost:18000":
        raise RuntimeError("Disposable integration runner required")
    with tempfile.TemporaryDirectory(prefix="atep-tls-") as temporary:
        directory = Path(temporary)
        certificates(directory)
        env = dict(os.environ, ATEP_ACCEPTANCE_TLS_DIRECTORY=directory.as_posix())
        compose = ["docker", "compose", "-p", project]
        for name in (
            "compose.integration.yaml",
            "compose.proxy-acceptance.yaml",
            "compose.proxy-tls-acceptance.yaml",
        ):
            compose.extend(["-f", str(ROOT / name)])
        try:
            command([*compose, "up", "-d", "--no-build", "--pull", "never", "api", "proxy"], env)
            api_id = command([*compose, "ps", "-q", "api"], env)
            ports = json.loads(
                command(
                    ["docker", "inspect", "--format", "{{json .HostConfig.PortBindings}}", api_id]
                )
            )
            assert not ports, "Backend must have no host port bindings"
            for closed in (18000, port(PROXY_HTTP)):
                with socket.socket() as probe:
                    probe.settimeout(2)
                    assert probe.connect_ex(("127.0.0.1", closed)) != 0
            print("PASS: API has no published ports; former API/HTTP ports are closed", flush=True)
            asyncio.run(acceptance(directory / "server.crt"))
            if lifecycle:
                from tools.dashboard_certificate_lifecycle import lifecycle_acceptance

                lifecycle_acceptance(directory, compose, env)
        finally:
            # Stop the key consumer before the temporary directory is removed.
            command([*compose, "stop", "proxy"], env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--lifecycle", action="store_true")
    try:
        args = parser.parse_args()
        main(args.project, lifecycle=args.lifecycle)
    except Exception as error:
        print(f"TLS acceptance failed: {type(error).__name__}", flush=True)
        raise SystemExit(1) from None
