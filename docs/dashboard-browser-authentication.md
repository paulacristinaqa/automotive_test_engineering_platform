# Dashboard browser authentication — X-6.7

## Decision and scope

Use a separate `/api/v1/dashboard/browser-stream/{view}` endpoint with exact Origin admission
and a bounded first-message bearer exchange. Preserve `/api/v1/dashboard/stream/{view}` for
native clients with Authorization headers and no Origin. Both routes share the same semaphore,
Redis handshake budget, JWT validation, live user/RBAC checks, snapshots and resource limits.

The design follows the first-message option described in the
[websockets authentication documentation](https://websockets.readthedocs.io/en/16.0/topics/authentication.html).
Unlike native header authentication, invalid credentials are rejected after HTTP upgrade, with
a WebSocket close code rather than an HTTP authentication status. No ticket store, new identity
provider, cookie login or paid service is added.

## Configuration

`ATEP_DASHBOARD_BROWSER_ORIGINS` defaults to empty: all browser handshakes are denied.
Set a comma-separated list of at most 20 exact origins, without trailing slash, path, wildcard,
credentials, query or fragment. Use HTTPS; HTTP is accepted only for `localhost`, `127.0.0.1`
and `::1` development origins. Example: `http://localhost:8080,https://dashboard.example.com`.
Origin strings are compared exactly, including the port; use the serialized Origin sent by
the client. An absent, duplicate, empty, null or unlisted Origin fails before admission work.
The integration Compose topology enables only `http://localhost:8080` for protocol tests.
Production/default deployments are not enabled by this change.

Require WSS/TLS in deployment and correctly configured trusted proxies. HTTP CORS settings do
not authorize WebSockets. This increment does not enable REST CORS: browser login requires a
same-origin API deployment or a separately reviewed HTTP CORS policy. Origin is not identity: non-browser clients can forge it, and all
clients still need a valid token and `dashboard:read`. Cookies are ignored for authentication.
Authorization headers and all query parameters are rejected on this browser-specific route.
Do not log WebSocket frames, enable protocol DEBUG tracing, capture authentication bodies or
put tokens in URLs, cookies or browser persistent storage. Keep the token in client memory.

## Versioned client exchange

Obtain an access token through the existing REST login contract, then open the browser route.
Within five seconds after acceptance, send one UTF-8 text JSON message:

```json
{"type":"atep.dashboard.authenticate.v1","access_token":"<access token>"}
```

These are the only accepted fields; the token must be a non-empty string. The complete encoded
message must be at most 4096 bytes. Binary, malformed, oversized or late messages close with
4401 and a generic reason, without echoing input. This is an application-level size check after
ASGI receive; deployment-level ingress/frame buffering limits must also be configured. It is
not a claim that the server never buffers a larger incoming frame.

No snapshot or database export is produced until token and live permission checks succeed.
Successful authentication produces the existing `atep.dashboard.snapshot.v1` stream; there is
no separate authentication acknowledgement. Invalid/expired credentials close with 4401 and
missing permission with 4403. Disabled/disallowed transport is denied before upgrade (HTTP 403
with the current ASGI server). Capacity or Redis rejection is also before acceptance.

The five-second authentication wait is inside a ten-second initial admission/authentication
budget. Pending authentication occupies one of 16 shared worker slots and consumes the shared
30-attempt/60-second peer quota. Cancellation, disconnect and failed authentication release the
owned slot. Subsequent messages are rejected as read-only (1008); refresh or reauthentication
requires reconnecting with backoff. The token is revalidated before and after every snapshot
query, so expiry, inactive users and revoked permissions cannot authorize later snapshots.
Revocation is checked on refresh, not pushed immediately during the 30-second wait.

## Evidence and remaining acceptance

Unit tests cover strict configuration, origins, framing, timeout, cancellation, rejection before
snapshot work and repeated token checks. Docker integration covers a valid first-message token,
unlisted Origin, invalid token and a user lacking permission, alongside the unchanged native flow.
These are backend and real-protocol tests, not visual/browser-engine or Android acceptance.
X-7 must verify actual browser/AAOS clients, reconnect, staleness, TLS/proxy deployment and
resource behavior. X-6 backend implementation is complete within this bounded scope; no
production-scale capacity, real-time vehicle telemetry or safety certification is claimed.
