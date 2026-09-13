# Dashboard cross-platform acceptance gates

X-7 must record actual platform, client version, command/scenario, result and retained evidence.
Backend tests do not establish graphical client acceptance or automotive safety certification.

| Surface | Required acceptance scenario | Current evidence boundary |
|---|---|---|
| Windows Python backend | Unit contracts, lint and types | Local automated suite |
| Linux containers | Authenticated snapshot, forbidden role, exports and read-only queries | Docker integration suite |
| Android/AAOS client | Header-based authentication, reconnect, stale indicator and permission loss | Not validated by backend tests |
| Browser dashboard | Approved authentication design, origin protection, reconnect and expired-session behavior | Native WebSocket cannot set an Authorization header; unsupported until designed |
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

X-6 remains in progress; this matrix defines gates, it does not claim they all passed.
