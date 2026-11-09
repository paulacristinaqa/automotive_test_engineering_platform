# X-7.20 — Local reverse-proxy identity boundary

## Scope

This first deployment increment validates trusted forwarding and the existing
Redis dashboard handshake budget through real Nginx. It is an opt-in HTTP
loopback fixture, NOT a production deployment or a passed TLS gate. No paid
cloud service, public endpoint or emulator is required.

The overlay `compose.proxy-acceptance.yaml` gives Nginx address `172.30.241.10`
on a dedicated `172.30.241.0/24` Docker network. Uvicorn trusts only that exact
address, not `*`, localhost or the whole subnet. A subnet conflict must fail
setup rather than broaden trust. Nginx replaces X-Forwarded-For and
X-Forwarded-Proto from its actual transport/scheme, replaces X-Real-IP, and
removes Forwarded and X-Forwarded-Client-Cert. It never appends untrusted chains.

The proxy is published only on `127.0.0.1:18800`, runs as UID/GID 101 without
Linux capabilities, with a read-only filesystem, 8 MiB temporary memory,
64 MiB container memory, 0.25 CPU and 32-process cap. The official image is
pinned by digest. One worker, bounded headers/body waits, disabled access logs,
no caching/buffering and explicit WebSocket Upgrade handling are configured.
These settings are safety bounds for this small fixture, not load-tested
production capacity guarantees.

## Tests and objectives

| Test | Objective |
|---|---|
| Exact trusted peer, two forwarded addresses | The installed Uvicorn middleware supplies the expected hashed client bucket and wss scheme. |
| Untrusted neighbor and localhost | Forged forwarding headers cannot alter identity or scheme. |
| Real proxy login and snapshot | The actual Nginx/API path supports authenticated native WebSocket upgrade and a versioned snapshot. |
| Rotating duplicate X-Forwarded-For and Forwarded claims | Requests still consume one Redis identity bucket, not attacker-selected buckets. |
| Attempts 30 and 31 | After 29 rejected credential handshakes, a valid token is admitted at 30 and denied at 31. |
| Redis TTL | The observed bucket is 31 with a positive TTL no greater than 60 seconds. |

The real test identifies the proxy's bucket by a before/after Redis comparison,
then resets only that disposable bucket for deterministic isolation. It never
flushes Redis. Attempts are sequential under a 40-second overall bound and
five-second opening timeout. Denied upgrades are checked as HTTP 403 responses
using real WebSocket Upgrade headers, avoiding a WebSocket close lifecycle for
a connection that was never upgraded. The accepted stream uses the WebSocket
client with a 200 ms close timeout. No application policy is shortened.
Credentials and raw responses are suppressed.

## Reproduction

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardProxyAcceptance -UseExistingImages
```

Only reuse images matching backend source. The pinned Nginx image must be
available locally when using `-UseExistingImages`; otherwise omit the switch
for normal Compose image/build behavior. Do not combine with AAOS scenarios.
The runner executes backend integration, proxy acceptance, restore verification
and cleanup sequentially. Unit/type checks use the local source tree:

```powershell
$env:MYPYPATH = 'src'
.venv\Scripts\python.exe -m pytest tests/test_dashboard_proxy_boundary.py tests/test_dashboard_admission.py -q
.venv\Scripts\python.exe -m mypy tools/run_dashboard_proxy_acceptance.py tests/test_dashboard_proxy_boundary.py
```

## Explicit remaining gates

TLS certificate verification, public deployment, upstream isolation, multi-worker
deployment behavior and resource-exhaustion tests are not established here.
The base integration API remains exposed on its existing test port; this is
not a production topology. Never expose this HTTP fixture publicly or trust
the sample IP without reproducing its network isolation. NAT peers share a
bucket; this is not a distributed concurrent-session cap. Next is local TLS
and upstream isolation, with independently verified certificates.

## References

- [Nginx WebSocket proxying](https://nginx.org/en/docs/http/websocket.html)
- [Nginx proxy header replacement](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header)
- The installed Uvicorn `ProxyHeadersMiddleware` implementation was inspected
  locally; tests exercise it rather than assuming forwarded headers are trusted.

## Evidence — 2026-09-17

The real proxy acceptance passed: one observed Redis identity bucket despite
rotating duplicate forwarding claims, a valid versioned snapshot at attempt
30 and HTTP 403 at attempt 31 with the same valid credential. The bucket count
was 31 and its TTL remained within the existing 60-second policy. Both backend
integration tests passed in 18.68 seconds. All ten targeted unit tests passed
again in 0.62 seconds; Ruff, strict mypy and diff checks passed.

Nginx 1.30.5 ran from the pinned image. Docker inspection confirmed 67,108,864
bytes memory, 250,000,000 NanoCPUs, 32 PIDs, read-only root and user 101:101.
Sampled host CPU was 36–57%, GPU 5–20%; one sample retained 14.0 GiB free RAM.
These are intermittent samples, not peaks or stress/capacity measurements.

Earlier attempts are not hidden: initial startup failed because default
FastCGI temporary directories were outside writable tmpfs; isolated `nginx -t`
identified this, and all temporary paths were moved under `/tmp`. Subsequent
WebSocket-client denial loops exceeded the 40-second bound even after reducing
close timeout. Denials now use HTTP Upgrade probes; the successful stream still
uses a real WebSocket client. No server admission or authentication policy was
weakened. English Markdown is updated; DOCX is unchanged. No commit/PR/merge
was performed in this increment.

Final restore passed with 87 tables/283 rows in 76.719 seconds. All owned
integration/proxy containers and networks were removed by the runner; a final
container query confirmed none remained. Final sampled CPU was 35%, GPU 7%.
Changes remain local and uncommitted.
