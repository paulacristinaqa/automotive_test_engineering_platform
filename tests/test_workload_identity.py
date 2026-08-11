from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi import Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings
from atep.core.errors import InvalidModuleCredentialError, ModuleCapabilityRequiredError
from atep.core.security import hash_module_token
from atep.registry.models import ModuleCapability, PlatformModule
from atep.registry.service import authenticate_module
from atep.registry.workload_identity import (
    module_authentication,
    parse_spiffe_module_identity,
)

JWT_SECRET = "test-secret-that-is-longer-than-32-characters"
TOKEN = "module-token-longer-than-thirty-two-characters"


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "jwt_secret": JWT_SECRET,
        "workload_identity_enabled": True,
        "workload_identity_trust_domain": "prod.atep.example",
        "workload_identity_trusted_proxy_cidrs": "10.42.0.0/16, 2001:db8::/32",
    }
    values.update(overrides)
    return Settings(**values)


def request_from(host: str) -> Request:
    return Request({"type": "http", "client": (host, 43210), "headers": []})


def module() -> PlatformModule:
    return PlatformModule(
        id=uuid4(),
        name="vehicle-gateway",
        display_name="Vehicle Gateway",
        description="",
        version="1.0.0",
        base_url=None,
        status="active",
        heartbeat_token_hash=hash_module_token(TOKEN),
        capabilities=[
            ModuleCapability(
                name="vehicle.telemetry.publish",
                version="1.0.0",
                description="",
            )
        ],
    )


class ModuleSession:
    def __init__(self, target: PlatformModule) -> None:
        self.target = target

    async def get(self, _: type[PlatformModule], identifier: object) -> PlatformModule | None:
        return self.target if identifier == self.target.id else None


def test_settings_normalize_trusted_proxy_networks_and_reject_invalid_values() -> None:
    configured = settings()
    assert configured.workload_identity_trust_domain == "prod.atep.example"
    assert configured.workload_identity_trusted_proxy_cidrs == "10.42.0.0/16,2001:db8::/32"

    with pytest.raises(ValidationError, match="trust domain"):
        settings(workload_identity_trust_domain="https://not-a-trust-domain")
    with pytest.raises(ValidationError):
        settings(workload_identity_trusted_proxy_cidrs="not-a-network")


def test_xfcc_parser_accepts_one_exact_spiffe_module_identity() -> None:
    assert (
        parse_spiffe_module_identity(
            "By=spiffe://prod.atep.example/proxy;Hash=abc123;"
            "URI=spiffe://prod.atep.example/atep/module/vehicle-gateway",
            expected_trust_domain="prod.atep.example",
        )
        == "vehicle-gateway"
    )


@pytest.mark.parametrize(
    "value",
    [
        "URI=spiffe://other.example/atep/module/vehicle-gateway",
        "URI=spiffe://prod.atep.example/other/vehicle-gateway",
        "URI=spiffe://prod.atep.example/atep/module/vehicle-gateway?role=admin",
        "URI=spiffe://prod.atep.example/atep/module/vehicle%2Dgateway",
        "URI=spiffe://prod.atep.example/atep/module/vehicle-gateway,URI=spiffe://prod.atep.example/atep/module/bms",
        "URI=spiffe://prod.atep.example/atep/module/vehicle-gateway;URI=spiffe://prod.atep.example/atep/module/bms",
        '[{"uri":["spiffe://prod.atep.example/atep/module/vehicle-gateway"]}]',
    ],
)
def test_xfcc_parser_rejects_ambiguous_or_noncanonical_identity(value: str) -> None:
    with pytest.raises(InvalidModuleCredentialError):
        parse_spiffe_module_identity(value, expected_trust_domain="prod.atep.example")


def test_identity_header_requires_enabled_mode_and_a_trusted_proxy() -> None:
    xfcc = "URI=spiffe://prod.atep.example/atep/module/vehicle-gateway"
    resolved = module_authentication(request_from("10.42.7.9"), settings(), TOKEN, xfcc)
    assert resolved.token is None
    assert resolved.spiffe_module_name == "vehicle-gateway"

    with pytest.raises(InvalidModuleCredentialError):
        module_authentication(request_from("192.0.2.10"), settings(), TOKEN, xfcc)
    with pytest.raises(InvalidModuleCredentialError):
        module_authentication(
            request_from("10.42.7.9"),
            settings(workload_identity_enabled=False),
            TOKEN,
            xfcc,
        )


def test_absent_identity_header_preserves_token_migration_path() -> None:
    resolved = module_authentication(request_from("192.0.2.10"), settings(), TOKEN, None)
    assert resolved.token == TOKEN
    assert resolved.spiffe_module_name is None


@pytest.mark.asyncio
async def test_spiffe_identity_authenticates_exact_module_and_preserves_capability_check() -> None:
    target = module()
    session = cast(AsyncSession, ModuleSession(target))
    authenticated = await authenticate_module(
        session,
        module_id=target.id,
        token=None,
        spiffe_module_name="vehicle-gateway",
        required_capability="vehicle.telemetry.publish",
    )
    assert authenticated is target

    with pytest.raises(InvalidModuleCredentialError):
        await authenticate_module(
            session,
            module_id=target.id,
            token=TOKEN,
            spiffe_module_name="bms",
        )
    with pytest.raises(ModuleCapabilityRequiredError):
        await authenticate_module(
            session,
            module_id=target.id,
            token=None,
            spiffe_module_name="vehicle-gateway",
            required_capability="vehicle.commands.consume",
        )
