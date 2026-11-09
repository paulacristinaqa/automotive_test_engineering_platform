"""Sequential, loopback-only acceptance of a real Nginx forwarding boundary."""

import argparse
import asyncio
import hashlib
import json
import os

import httpx
import redis.asyncio as redis
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from tools.run_dashboard_tls_acceptance import command

PREFIX = b"atep:rate-limit:dashboard-handshake:peer:"


async def counts(client: redis.Redis) -> dict[bytes, int]:
    result: dict[bytes, int] = {}
    async for key in client.scan_iter(match=PREFIX + b"*", count=100):
        value = await client.get(key)
        if value is not None:
            result[key] = int(value)
    return result


def target(index: int, multi_process: bool) -> tuple[int, str | None]:
    if not multi_process:
        return 18800, None
    return (18801, "172.30.241.20:8000") if index % 2 else (18802, "172.30.241.21:8000")


def verify_upstream(actual: str | None, expected: str | None) -> None:
    if expected is not None and actual != expected:
        raise RuntimeError("Request did not reach the expected independent replica")


def verify_replicas(project: str) -> None:
    identities: set[str] = set()
    processes: set[int] = set()
    for service in ("api", "api-peer"):
        container = command(
            [
                "docker",
                "ps",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--filter",
                f"label=com.docker.compose.service={service}",
            ]
        )
        record = json.loads(
            command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"id":{{json .Id}},"pid":{{.State.Pid}},"memory":{{.HostConfig.Memory}},'
                    '"cpu":{{.HostConfig.NanoCpus}},"pids":{{.HostConfig.PidsLimit}}}',
                    container,
                ]
            )
        )
        if record["pid"] <= 0 or (record["memory"], record["cpu"], record["pids"]) != (
            536870912,
            500000000,
            64,
        ):
            raise RuntimeError("Replica is not running with the expected resource bounds")
        identities.add(record["id"])
        processes.add(record["pid"])
    if len(identities) != 2 or len(processes) != 2:
        raise RuntimeError("Two independent processes are required")
    print("PASS: two independent API processes, each 512 MiB / 0.5 CPU / 64 PIDs", flush=True)


async def main(*, multi_process: bool = False) -> None:
    if os.environ.get("ATEP_INTEGRATION_API_URL") != "http://localhost:18000":
        raise RuntimeError("Disposable runner required")
    client = redis.Redis.from_url("redis://127.0.0.1:16379/0", socket_timeout=2)
    print("Proxy acceptance: authenticating through loopback Nginx", flush=True)
    port, _ = target(1, multi_process)
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False
    ) as api:
        response = await api.post(
            "/api/v1/auth/token",
            data={
                "username": os.environ["ATEP_INTEGRATION_ADMIN_EMAIL"],
                "password": os.environ["ATEP_INTEGRATION_ADMIN_PASSWORD"],
            },
        )
        response.raise_for_status()
        token = response.json()["access_token"]

    async def attempt(index: int, *, authorized: bool = False, accepted: bool = False) -> None:
        port, expected_upstream = target(index, multi_process)
        headers = [
            ("Authorization", f"Bearer {token}" if authorized else "Bearer invalid-fixture"),
            ("X-Forwarded-For", f"198.51.100.{index}"),
            ("X-Forwarded-For", f"203.0.113.{index}, 127.0.0.1"),
            ("X-Forwarded-Proto", "https"),
            ("Forwarded", f"for=198.51.100.{index};proto=https"),
        ]
        if not accepted:
            # A refused WebSocket upgrade is an HTTP response, not an open
            # WebSocket. Read that response without a WebSocket close lifecycle.
            headers += [
                ("Connection", "Upgrade"),
                ("Upgrade", "websocket"),
                ("Sec-WebSocket-Version", "13"),
                ("Sec-WebSocket-Key", "dGhlIHNhbXBsZSBub25jZQ=="),
            ]
            async with httpx.AsyncClient(timeout=5, trust_env=False) as probe:
                denied = await probe.get(
                    f"http://127.0.0.1:{port}/api/v1/dashboard/stream/operations", headers=headers
                )
                verify_upstream(denied.headers.get("X-Atep-Acceptance-Upstream"), expected_upstream)
                if denied.status_code != 403:
                    raise RuntimeError("Unexpected rejected-upgrade status")
            return
        try:
            async with connect(
                f"ws://127.0.0.1:{port}/api/v1/dashboard/stream/operations",
                additional_headers=headers,
                open_timeout=5,
                close_timeout=0.2,
                proxy=None,
            ) as socket:
                if socket.response is None:
                    raise RuntimeError("Missing upgrade response")
                verify_upstream(
                    socket.response.headers.get("X-Atep-Acceptance-Upstream"), expected_upstream
                )
                if not accepted:
                    raise RuntimeError("Unexpected admitted stream")
                frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
                if frame["type"] != "atep.dashboard.snapshot.v1" or frame["sequence"] != 1:
                    raise RuntimeError("Invalid proxied snapshot")
        except InvalidStatus as error:
            if accepted or error.response.status_code != 403:
                raise RuntimeError("Unexpected proxy handshake status") from None

    key: bytes | None = None
    try:
        async with asyncio.timeout(40):
            print("Proxy acceptance: identifying the forwarded peer bucket", flush=True)
            before = await counts(client)
            await attempt(1, authorized=multi_process, accepted=multi_process)
            after = await counts(client)
            changed = [item for item in after if after[item] == before.get(item, 0) + 1]
            if len(changed) != 1:
                raise RuntimeError("Cannot isolate the disposable proxy peer counter")
            key = changed[0]
            if multi_process:
                # Prove both processes can serve data before testing denial.
                await attempt(2, authorized=True, accepted=True)
                if int(await client.get(key) or 0) != after[key] + 1:
                    raise RuntimeError("The second process did not consume the same Redis bucket")
            # Reset only the observed fixture bucket, never the Redis database.
            await client.delete(key)
            baseline = await counts(client)
            print("Proxy acceptance: checking spoofing and the 30/31 boundary", flush=True)
            for index in range(1, 30):
                await attempt(index)
                if index % 10 == 0:
                    print(f"Proxy acceptance: {index} sequential denials checked", flush=True)
            await attempt(30, authorized=True, accepted=True)
            await attempt(31, authorized=True)
            if multi_process:
                await attempt(32, authorized=True)
            final = await counts(client)
            expected_count = 32 if multi_process else 31
            if final.get(key) != expected_count or not 0 < await client.pttl(key) <= 60_000:
                raise RuntimeError("Shared handshake budget was not enforced")
            for item, value in final.items():
                if item != key and value != baseline.get(item):
                    raise RuntimeError("Spoofed headers created another identity bucket")
            for index in range(1, expected_count + 1):
                forged = (
                    PREFIX + hashlib.sha256(f"198.51.100.{index}".encode()).hexdigest().encode()
                )
                if key == forged:
                    raise RuntimeError("Client-controlled identity was trusted")
            print(
                "PASS: Nginx snapshot; duplicate/spoofed headers share one Redis bucket; "
                "attempt 30 accepted and attempt 31 denied"
            )
            if multi_process:
                print("PASS: alternating replicas share one budget; both deny after exhaustion")
    finally:
        if key is not None:
            await client.delete(key)
        await client.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--multi-process", action="store_true")
    parser.add_argument("--project", default="atep-integration")
    args = parser.parse_args()
    try:
        if args.multi_process:
            verify_replicas(args.project)
        asyncio.run(main(multi_process=args.multi_process))
    except Exception as error:
        print(
            f"Proxy acceptance failed ({type(error).__name__}); "
            "credentials and raw responses suppressed"
        )
        raise SystemExit(1) from None
