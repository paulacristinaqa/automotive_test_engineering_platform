from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from atep.core.config import Settings
from atep.core.rate_limit import _client_identity
from atep.core.security import create_access_token, metrics_request_authorized

JWT_SECRET = "hardening-test-secret-that-is-longer-than-32-characters"
METRICS_TOKEN = "metrics-scrape-token-that-is-longer-than-32-characters"


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"_env_file": None, "jwt_secret": JWT_SECRET}
    values.update(overrides)
    return Settings(**values)


def request(authorization: str | None = None, host: str = "203.0.113.7") -> Request:
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    scope = {"type": "http", "headers": headers, "client": (host, 50000)}
    return Request(scope)


@pytest.mark.parametrize(
    "secret",
    [
        "replace-with-at-least-32-random-characters",
        "CHANGE-ME-please-this-is-not-a-real-secret-value",
        "x" * 40,
    ],
)
def test_example_or_repetitive_jwt_secrets_are_rejected(secret: str) -> None:
    with pytest.raises(ValidationError):
        settings(jwt_secret=secret)


@pytest.mark.parametrize("algorithm", ["none", "RS256", "hs256"])
def test_only_supported_hmac_algorithms_are_accepted(algorithm: str) -> None:
    with pytest.raises(ValidationError):
        settings(jwt_algorithm=algorithm)


def test_production_requires_a_metrics_token_when_metrics_are_enabled() -> None:
    with pytest.raises(ValidationError, match="ATEP_METRICS_BEARER_TOKEN"):
        settings(environment="production")
    assert settings(environment="production", metrics_enabled=False).metrics_enabled is False
    configured = settings(environment="production", metrics_bearer_token=METRICS_TOKEN)
    assert configured.metrics_bearer_token is not None


def test_metrics_token_is_required_only_when_configured() -> None:
    open_settings = settings()
    protected = settings(metrics_bearer_token=METRICS_TOKEN)

    assert metrics_request_authorized(request(), open_settings)
    assert not metrics_request_authorized(request(), protected)
    assert not metrics_request_authorized(request("Bearer wrong-token"), protected)
    assert not metrics_request_authorized(request(f"Basic {METRICS_TOKEN}"), protected)
    assert metrics_request_authorized(request(f"Bearer {METRICS_TOKEN}"), protected)


def test_metrics_endpoint_rejects_scrapes_without_the_configured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atep import main

    protected = settings(metrics_bearer_token=METRICS_TOKEN)
    monkeypatch.setattr(main, "settings", protected)
    client = TestClient(main.app)

    assert client.get("/metrics").status_code == 401
    authorized = client.get("/metrics", headers={"Authorization": f"Bearer {METRICS_TOKEN}"})
    assert authorized.status_code == 200


def test_rate_limit_identity_ignores_unverified_authorization_headers() -> None:
    config = settings()
    anonymous = _client_identity(request(), config)

    assert _client_identity(request("Bearer junk-1"), config) == anonymous
    assert _client_identity(request("Bearer junk-2"), config) == anonymous
    assert _client_identity(request("Basic abc"), config) == anonymous


def test_rate_limit_identity_uses_the_verified_user_across_addresses() -> None:
    config = settings()
    token = create_access_token(uuid4(), config)

    first = _client_identity(request(f"Bearer {token}", host="198.51.100.1"), config)
    second = _client_identity(request(f"Bearer {token}", host="198.51.100.2"), config)

    assert first == second
    assert first.startswith("user:")


def test_rate_limit_identity_handles_missing_client() -> None:
    scope = cast(dict[str, Any], {"type": "http", "headers": [], "client": None})
    identity = _client_identity(Request(scope), settings())
    assert identity.startswith("client:")
