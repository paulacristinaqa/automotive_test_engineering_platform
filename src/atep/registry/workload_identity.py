from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Header, Request

from atep.core.config import Settings, get_settings
from atep.core.errors import InvalidModuleCredentialError
from atep.registry.schemas import MODULE_NAME_PATTERN

XFCC_HEADER = "X-Forwarded-Client-Cert"
SPIFFE_MODULE_PREFIX = "/atep/module/"


@dataclass(frozen=True)
class ModuleAuthentication:
    token: str | None
    spiffe_module_name: str | None


def module_authentication(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    module_token: Annotated[
        str | None,
        Header(alias="X-ATEP-Module-Token", min_length=32, max_length=512),
    ] = None,
    forwarded_client_cert: Annotated[
        str | None,
        Header(alias=XFCC_HEADER, max_length=4096),
    ] = None,
) -> ModuleAuthentication:
    if forwarded_client_cert is None:
        return ModuleAuthentication(token=module_token, spiffe_module_name=None)
    if not settings.workload_identity_enabled or not _is_trusted_proxy(request, settings):
        raise InvalidModuleCredentialError()
    module_name = parse_spiffe_module_identity(
        forwarded_client_cert,
        expected_trust_domain=settings.workload_identity_trust_domain,
    )
    return ModuleAuthentication(token=None, spiffe_module_name=module_name)


def parse_spiffe_module_identity(value: str, *, expected_trust_domain: str) -> str:
    if not value.isascii() or len(value) > 4096 or "," in value:
        raise InvalidModuleCredentialError()
    uri_values: list[str] = []
    for field in value.split(";"):
        key, separator, field_value = field.partition("=")
        if not separator:
            raise InvalidModuleCredentialError()
        if key.strip().casefold() == "uri":
            uri_values.append(field_value.strip())
    if len(uri_values) != 1:
        raise InvalidModuleCredentialError()
    return _module_name_from_spiffe_id(uri_values[0], expected_trust_domain=expected_trust_domain)


def _module_name_from_spiffe_id(value: str, *, expected_trust_domain: str) -> str:
    if len(value) > 2048 or "%" in value or '"' in value:
        raise InvalidModuleCredentialError()
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() != "spiffe"
        or parsed.hostname is None
        or parsed.hostname.casefold() != expected_trust_domain.casefold()
        or parsed.netloc.casefold() != parsed.hostname.casefold()
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(SPIFFE_MODULE_PREFIX)
    ):
        raise InvalidModuleCredentialError()
    module_name = parsed.path.removeprefix(SPIFFE_MODULE_PREFIX)
    if not MODULE_NAME_PATTERN.fullmatch(module_name):
        raise InvalidModuleCredentialError()
    return module_name


def _is_trusted_proxy(request: Request, settings: Settings) -> bool:
    if request.client is None:
        return False
    try:
        source = ip_address(request.client.host)
        networks = [
            ip_network(item)
            for item in settings.workload_identity_trusted_proxy_cidrs.split(",")
            if item
        ]
    except ValueError:
        return False
    return any(source in network for network in networks)
