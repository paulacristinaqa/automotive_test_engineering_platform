# Dashboard cross-platform acceptance gates

X-7 must record actual platform, client version, command/scenario, result and retained evidence.
Backend tests do not establish graphical client acceptance or automotive safety certification.

| Surface | Required acceptance scenario | Current evidence boundary |
|---|---|---|
| Windows Python backend | Unit contracts, lint and types | Local automated suite |
| Linux containers | Authenticated snapshot, forbidden role, exports and read-only queries | Docker integration suite |
| Android/AAOS client | Header-based authentication, reconnect, stale indicator and permission loss | Not validated by backend tests |
| Browser dashboard | Actual browser login/stream, origin protection, reconnect and expired-session behavior | X-7.2 fixture reconnect/stale evidence; X-7.4 real form login/logout/no-role shell evidence; final-shell lifecycle acceptance pending |
| Trusted reverse proxy | Transport peer integrity, shared quota, TLS and resource limits | Deployment acceptance pending |

Every supported client must distinguish server query time from vehicle measurement time, mark
disconnected snapshots stale, back off reconnect attempts and respect the 30-second refresh floor.
Verify a 10-snapshot session ends normally, unauthorized users obtain no data, and exports contain
neither credentials nor raw source logs. Test inactive-user and role-removal behavior at the next
authorization check; this is not instantaneous push revocation during the refresh wait.

Admission uses 16 slots per worker including handshakes and 30 attempts per 60-second fixed window
per ASGI transport peer in shared Redis. Authentication failures also consume the quota. Missing
peers share an `unknown` bucket. NAT/proxy users can share a budget. Do not trust arbitrary forwarded
headers: configure proxy trust explicitly. This is not a distributed concurrent-connection cap or
a production capacity guarantee. Redis outage denies new streams but does not forcibly end existing
ones. The limiter is always enabled, independently of the HTTP rate-limit configuration.

Before acceptance, a denial uses an ASGI close and may appear as HTTP 403 rather than a WebSocket
1013 frame. Clients must not expect HTTP rate-limit headers. Never place access tokens in URLs.
No browser workaround, new paid service, GPU workload or real vehicle command is introduced here.

X-6.6 enforces this native-only boundary rather than implicitly relying on lack of browser header
support. Every Origin value is rejected, including same-origin, empty and `null`; no browser origin
is currently allowed. Origin is not authentication and header omission is not proof of client type.
Native/AAOS clients must omit Origin and supply Authorization. Integration verifies real 403 denials
and native snapshot success; it does not exercise a browser UI or certify Android compatibility.

The Redis admission test uses two client pools, one random pseudonymous peer and 31 sequential
attempts under a ten-second timeout. It checks TTL and recovery by shortening only the test key's
TTL. This proves shared Redis counter behavior, not multi-process WebSocket capacity.

X-6 backend scope is implemented; this X-7 matrix does not claim every client/deployment gate passed.
The separate browser route is specified in `dashboard-browser-authentication.md`. The native
Origin prohibition above remains unchanged; it is not the policy of the new browser route.
