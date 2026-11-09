# X-7.21 — Local TLS and upstream isolation

## Scope and design

This disposable acceptance profile terminates TLS at the existing pinned Nginx
proxy. HTTPS and WSS use `localhost:18443`, published on IPv4 loopback only.
The TLS overlay removes **all API host port bindings**, replaces the proxy HTTP
binding, and retains the exact trusted proxy address from X-7.20. Internal
proxy-to-API traffic remains HTTP inside Docker; this is not mutual TLS.

The runner generates a one-day, self-signed RSA localhost certificate using
OpenSSL (PATH or the Git for Windows installation). The Python client explicitly
trusts that certificate while keeping certificate and hostname verification
enabled. Nothing is installed in the Windows, browser or Android trust store.
Keys live in a unique temporary directory, are mounted read-only, and are removed
after stopping the proxy. This is a local test certificate, not a production CA chain.

## Execution

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_integration_tests.ps1 -DashboardProxyTlsAcceptance
```

Compose 2.24.4 or later is required for the replacement tag. Docker Desktop and
the project Python development environment must be available. The optional
`-UseExistingImages` switch is only safe when the application image already
matches the source. No emulator, cloud account or paid API is involved.

The runner first performs the existing HTTP integration suite, then transitions
the same disposable stack to TLS and removes direct API publishing. Therefore
the earlier integration phase is **not** an isolated TLS deployment. After TLS
acceptance it stops writers, runs the existing restore drill, and removes the
owned stack. Other dependency ports retain the base integration configuration;
this profile is not a complete production network policy.

## Test objectives

| Check | Objective |
|---|---|
| Explicit trust context unit test | Retain CERT_REQUIRED, hostname checks and TLS 1.2 minimum |
| Negative-case oracle tests | Do not mistake success or a TCP failure for certificate rejection |
| TLS 1.2 and 1.3 handshakes | Verify both configured protocol versions actually negotiate |
| Default-trust rejection | Refuse the disposable certificate without explicit trust |
| Wrong-host rejection | Refuse a valid trusted certificate for a different hostname |
| HTTPS readiness and login | Exercise verified encryption and real authentication |
| WSS first snapshot | Exercise authenticated WebSocket upgrade and application data over TLS |
| Docker bindings plus TCP probes | Confirm no API host mappings and closed former API/HTTP ports |
| Restore and cleanup | Preserve the existing recovery gate and remove temporary resources |

## Boundaries

No public certificate issuance, renewal/rotation, expired certificate fixture,
revocation, browser/AAOS TLS trust, legacy-protocol negative test, mTLS, penetration
test, multi-worker capacity or production SLA is claimed. Docker peers on the
API network can still reach it; host-port isolation does not protect against a
compromised trusted container or Docker administrator. Resource limits are
inherited from X-7.20, not a demonstrated production capacity.

## References

- [Docker Compose merge and replacement rules](https://docs.docker.com/reference/compose-file/merge/)
- [Nginx SSL module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html#ssl_protocols)

## Evidence

On 2026-09-17, fourteen targeted unit tests passed (0.77 seconds), together with
Ruff and strict mypy for the new Python files. Two existing integration tests
passed in 18.20 seconds before the TLS transition. The real TLS gate passed all
checks listed above; restore verified 87 tables and 283 rows in 76.25 seconds
at migration `0064_ai_evidence_projections`. Owned containers, networks and TLS
temporary directories were absent after cleanup. CPU samples were 24–39% and
GPU samples 5–11%; these are intermittent readings, not peak measurements.
The existing application image was reused because this increment changes only
host acceptance tooling and mounted proxy configuration, not backend source.

The Nginx image did not include the OpenSSL CLI; certificate generation instead
used the already installed Git for Windows executable. No dependency installation
was needed. Markdown evidence is updated; DOCX and remote Git state are unchanged.
