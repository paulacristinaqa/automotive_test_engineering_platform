"""Local expired-certificate rejection and replacement; never modifies system trust."""

import asyncio
import hashlib
import shutil
import socket
import ssl
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tools.acceptance_ports import PROXY_TLS, port
from tools.run_dashboard_tls_acceptance import (
    acceptance,
    certificates,
    command,
    handshake,
    openssl_executable,
    rejected_certificate,
    trusted_context,
)


def expired_certificate(source: Path, destination: Path) -> None:
    destination.mkdir()
    shutil.copyfile(source / "server.key", destination / "server.key")
    now = datetime.now(UTC)
    command(
        [
            openssl_executable(),
            "x509",
            "-in",
            str(source / "server.crt"),
            "-signkey",
            str(destination / "server.key"),
            "-not_before",
            (now - timedelta(days=2)).strftime("%Y%m%d%H%M%SZ"),
            "-not_after",
            (now - timedelta(days=1)).strftime("%Y%m%d%H%M%SZ"),
            "-out",
            str(destination / "server.crt"),
        ]
    )


def require_expired(context: ssl.SSLContext) -> None:
    try:
        handshake(context, "localhost")
    except ssl.SSLCertVerificationError as error:
        # X509_V_ERR_CERT_HAS_EXPIRED. Other trust/hostname errors aren't expiry evidence.
        if error.verify_code == 10:
            return
        raise RuntimeError("Expected certificate expiration, not another trust error") from None
    raise RuntimeError("Expired certificate unexpectedly accepted")


def fingerprint(certificate: Path) -> str:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(certificate.read_text())).hexdigest()


def served_fingerprint(context: ssl.SSLContext) -> str:
    with socket.create_connection(("127.0.0.1", port(PROXY_TLS)), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname="localhost") as secured:
            certificate = secured.getpeercert(binary_form=True)
            if certificate is None:
                raise RuntimeError("Missing server certificate")
            return hashlib.sha256(certificate).hexdigest()


def wait_for_listener() -> None:
    for attempt in range(20):
        try:
            with socket.create_connection(("127.0.0.1", port(PROXY_TLS)), timeout=1):
                return
        except OSError:
            if attempt == 19:
                raise
            time.sleep(0.5)


def lifecycle_acceptance(directory: Path, compose: list[str], env: dict[str, str]) -> None:
    original = directory / "server.crt"
    original_context = trusted_context(original)
    expired = directory / "expired"
    replacement = directory / "replacement"
    expired_certificate(directory, expired)
    replacement.mkdir()
    certificates(replacement)
    if fingerprint(original) == fingerprint(replacement / "server.crt"):
        raise RuntimeError("Replacement certificate must differ")

    def replace_proxy(material: Path) -> None:
        selected = dict(env, ATEP_ACCEPTANCE_TLS_DIRECTORY=material.as_posix())
        command(
            [
                *compose,
                "up",
                "-d",
                "--no-deps",
                "--force-recreate",
                "--no-build",
                "--pull",
                "never",
                "proxy",
            ],
            selected,
        )
        wait_for_listener()

    replace_proxy(expired)
    require_expired(trusted_context(expired / "server.crt"))
    print(
        "PASS: explicitly trusted expired certificate rejected with verification code 10",
        flush=True,
    )
    replace_proxy(replacement)
    rejected_certificate(original_context, "localhost")
    context = trusted_context(replacement / "server.crt")
    if served_fingerprint(context) != fingerprint(replacement / "server.crt"):
        raise RuntimeError("Proxy is not serving the replacement certificate")
    asyncio.run(acceptance(replacement / "server.crt"))
    print(
        "PASS: old trust rejected; new certificate served; HTTPS/WSS recovery verified", flush=True
    )
