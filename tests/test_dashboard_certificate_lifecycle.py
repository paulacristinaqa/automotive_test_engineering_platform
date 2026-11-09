import ssl
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.dashboard_certificate_lifecycle import expired_certificate, fingerprint, require_expired
from tools.run_dashboard_tls_acceptance import certificates, command, openssl_executable


def test_expired_fixture_and_replacement_are_distinct(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(dir=tmp_path) as temporary:
        source = Path(temporary)
        certificates(source)
        expired = source / "expired"
        expired_certificate(source, expired)
        end = command(
            [openssl_executable(), "x509", "-in", str(expired / "server.crt"), "-noout", "-enddate"]
        )
        expiry = datetime.strptime(end.split("=", 1)[1], "%b %d %H:%M:%S %Y GMT").replace(
            tzinfo=UTC
        )
        assert expiry < datetime.now(UTC)
        replacement = source / "replacement"
        replacement.mkdir()
        certificates(replacement)
        assert (
            len({fingerprint(path / "server.crt") for path in (source, expired, replacement)}) == 3
        )
    assert not source.exists()


@pytest.mark.parametrize("code", [18, 62])
def test_other_certificate_errors_are_not_expiration(code: int) -> None:
    error = ssl.SSLCertVerificationError()
    error.verify_code = code
    with patch("tools.dashboard_certificate_lifecycle.handshake", side_effect=error):
        with pytest.raises(RuntimeError, match="another trust error"):
            require_expired(ssl.create_default_context())


def test_expiration_code_is_accepted() -> None:
    error = ssl.SSLCertVerificationError()
    error.verify_code = 10
    with patch("tools.dashboard_certificate_lifecycle.handshake", side_effect=error):
        require_expired(ssl.create_default_context())


def test_success_is_not_expiration() -> None:
    with patch("tools.dashboard_certificate_lifecycle.handshake", return_value="TLSv1.3"):
        with pytest.raises(RuntimeError, match="unexpectedly accepted"):
            require_expired(ssl.create_default_context())


def test_transport_failure_is_not_expiration() -> None:
    with patch(
        "tools.dashboard_certificate_lifecycle.handshake", side_effect=ConnectionRefusedError
    ):
        with pytest.raises(ConnectionRefusedError):
            require_expired(ssl.create_default_context())
