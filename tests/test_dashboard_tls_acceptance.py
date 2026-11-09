import ssl
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.run_dashboard_tls_acceptance import (
    certificates,
    rejected_certificate,
    trusted_context,
)


def test_explicit_trust_keeps_hostname_and_chain_validation(tmp_path: Path) -> None:
    with tempfile.TemporaryDirectory(dir=tmp_path) as temporary:
        directory = Path(temporary)
        certificates(directory)
        context = trusted_context(directory / "server.crt")
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.minimum_version == ssl.TLSVersion.TLSv1_2
        assert (directory / "server.key").is_file()
    assert not directory.exists()


def test_rejection_requires_a_certificate_error() -> None:
    with patch(
        "tools.run_dashboard_tls_acceptance.handshake", side_effect=ssl.SSLCertVerificationError
    ):
        rejected_certificate(ssl.create_default_context(), "localhost")


def test_successful_handshake_cannot_pass_negative_case() -> None:
    with patch("tools.run_dashboard_tls_acceptance.handshake", return_value="TLSv1.3"):
        with pytest.raises(AssertionError):
            rejected_certificate(ssl.create_default_context(), "localhost")


def test_transport_failure_cannot_pass_certificate_case() -> None:
    with patch("tools.run_dashboard_tls_acceptance.handshake", side_effect=ConnectionRefusedError):
        with pytest.raises(ConnectionRefusedError):
            rejected_certificate(ssl.create_default_context(), "localhost")
