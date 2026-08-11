# Workload identity and mTLS trust boundary

## Scope

ATEP can authenticate a registered platform module from a SPIFFE identity forwarded by an
approved mutual-TLS proxy. This is an initial application-side boundary: ATEP validates the
forwarded identity and continues to enforce the module's declared capabilities. Certificate
issuance, rotation, proxy deployment, and live mTLS evidence remain deployment responsibilities.

Human API clients continue to use JWT and RBAC. Android applications and modules never connect
directly to PostgreSQL, Redis, or RabbitMQ.

## Identity contract

The accepted SPIFFE ID is exactly:

```text
spiffe://<trust-domain>/atep/module/<canonical-module-name>
```

The trust domain is configured per environment. The module name must match the canonical name in
the ATEP registry. Query strings, fragments, percent encoding, multiple URI fields, multiple XFCC
elements, non-ASCII input, and alternate paths are rejected with `invalid_module_credential`.

The following module operations accept the identity:

- heartbeat;
- vehicle telemetry ingestion;
- vehicle-command claim;
- vehicle-command acknowledgement.

Capability checks remain unchanged. Identity proves which module is calling; it does not grant a
capability that the registry has not assigned.

## Trusted proxy contract

`X-Forwarded-Client-Cert` (XFCC) is security-sensitive and is accepted only when all of these are
true:

1. `ATEP_WORKLOAD_IDENTITY_ENABLED=true`;
2. the direct network peer belongs to `ATEP_WORKLOAD_IDENTITY_TRUSTED_PROXY_CIDRS`;
3. the proxy has completed client-certificate validation against the intended trust bundle;
4. the proxy removes caller-supplied XFCC and replaces it with its validated client identity;
5. the proxy emits one `URI=` field containing the exact SPIFFE ID.

For Envoy, the deployment policy should use `forward_client_cert_details: SANITIZE_SET` and enable
the URI field in `set_current_client_cert_details`. Direct paths to the ATEP pod must be denied;
CIDR trust is a second guard, not a replacement for network policy or mTLS.

If an XFCC header is present but the feature is disabled, the peer is not trusted, or the value is
invalid, ATEP rejects the request. It never downgrades that request to the legacy token.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `ATEP_WORKLOAD_IDENTITY_ENABLED` | `false` | Enables trusted-proxy SPIFFE authentication |
| `ATEP_WORKLOAD_IDENTITY_TRUST_DOMAIN` | `atep.local` | Exact environment trust domain |
| `ATEP_WORKLOAD_IDENTITY_TRUSTED_PROXY_CIDRS` | empty | Comma-separated direct-peer IPv4/IPv6 networks |

Keep the feature disabled in the common Kubernetes base. Enable it only in a reviewed environment
overlay after the proxy, trust bundle, network policy, and CIDRs are known. Use different trust
domains for development, staging, and production.

## Migration and rollback

When no XFCC header is present, the existing `X-ATEP-Module-Token` remains available as a migration
path. During migration, monitor which authentication method is used, move one module at a time,
then revoke its shared token after mTLS evidence is retained. Do not send both credentials as a
fallback strategy: a presented XFCC identity always takes precedence and must match exactly.

To roll back the proxy integration, stop forwarding XFCC and set the feature flag to `false`; keep
the module token available until the rollback window closes. Never disable certificate validation
or broaden trusted CIDRs to recover availability.

## Verification catalogue

| ID | Test | Objective |
|---|---|---|
| WID-001 | Valid trusted XFCC | Accept one canonical SPIFFE module identity |
| WID-002 | Trust-domain/path validation | Reject identities outside the configured namespace |
| WID-003 | Ambiguity validation | Reject multiple elements, multiple URI fields, encoding, query, and fragment variants |
| WID-004 | Trusted-peer enforcement | Reject XFCC from a direct peer outside the configured CIDRs |
| WID-005 | Disabled-mode enforcement | Reject a presented identity while workload identity is disabled |
| WID-006 | No-downgrade enforcement | Reject a mismatched SPIFFE identity even when a valid legacy token is also supplied |
| WID-007 | Migration compatibility | Continue token authentication when XFCC is absent |
| WID-008 | Capability preservation | Authenticate identity but deny an undeclared module capability |
| WID-009 | Live proxy mTLS scenario | Prove certificate validation, XFCC replacement, rotation, revocation, and direct-path denial (pending) |

## References

- [SPIFFE ID specification](https://spiffe.io/docs/latest/spiffe-specs/spiffe-id/)
- [SPIFFE trust domains](https://spiffe.io/docs/latest/spiffe/concepts/)
- [SPIRE mTLS use case](https://spiffe.io/docs/latest/spire-about/use-cases/)
- [Envoy XFCC processing](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/headers.html)
- [Envoy HTTP connection manager API](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/network/http_connection_manager/v3/http_connection_manager.proto.html)
