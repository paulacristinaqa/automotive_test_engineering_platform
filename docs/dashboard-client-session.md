# X-7.3 — Dashboard session controller foundation

## Architecture and scope

`clients/dashboard/session-client.mjs` connects a future login form, the existing identity
REST API and `DashboardStreamClient`. This is a unit-tested foundation, not completed
end-user login/UI acceptance. No public routes, hosting, CORS changes or dependencies are added.

Login uses URL-encoded username/password at `/api/v1/auth/token`, matching FastAPI's
OAuth2PasswordRequestForm, not JSON. Requests are same-origin, omit cookies, disallow redirects
and request no-store caching. The host must serve API and UI under the same HTTPS origin
(HTTP is suitable only for local development). The UI must supply a trusted stream URL on that
origin and configure the backend's exact browser Origin allowlist.

The stream holds the access token privately; the controller holds the refresh token privately
only for logout. Public state contains status/reason. No storage, cookies, logs, token URLs or
automatic refresh are implemented. Reloading requires login. Reference removal is not memory
zeroization or protection against XSS, browser debugging or consumer-retained copies.

## Integration and lifecycle

1. Submit through `login(username, password)` and clear the password input in the future UI.
2. Duplicate submissions are suppressed. `signed_in` means REST authentication succeeded,
   not that snapshot delivery or dashboard authorization has succeeded.
3. Forward stream `onState` to `session.handleStreamState(state)` as well as rendering it.
   Authentication/permission rejection clears the session; stale data is a transport concern.
4. Expiration stops the stream and clears local references. The advertised lifetime is reduced
   by the full ten-second request deadline, conservatively accounting for request latency.
5. Logout clears local state first, then posts the refresh token to `/api/v1/auth/logout`.
   Only HTTP 204 confirms revocation; failure reports `revocation_unconfirmed`.
6. `dispose()` cancels work and clears references/timers, without confirming server logout.

Requests have a ten-second deadline including body parsing. Generation counters prevent late
responses from resurrecting sessions. Parsed response text is capped at 16 KiB after browser
buffering; this is not a network-layer payload limit. Injected dependencies and callbacks are
trusted application code; callbacks must not throw, log credentials or retain stopped snapshots.

Logout revokes refresh sessions, not already-issued access JWTs everywhere. An aborted login
may already have created a server session; without its response the client cannot revoke that
unknown token. Server expiry/revocation policy remains authoritative. Login/logout are not retried
automatically. Very short advertised access lifetimes expire locally immediately.

## Tests and evidence

The 14 new Node tests cover form encoding, request policies, secret-free public state, bounded
inputs/token contracts, stable 401/403/429/500 failures without reading error bodies, duplicate
suppression, cancellation and late responses, fetch ignoring abort, expiration, immediate local
logout cleanup, remote logout contract, offline revocation uncertainty, terminal stream rejection,
re-login and disposal during logout. Virtual clocks avoid load or long waits.

Local verification on 2026-09-14: 594 Python tests passed (two integration tests deselected),
Ruff passed and mypy passed over 241 files. During regression a whole-host sample was CPU 37%,
GPU 11%, GPU memory 693 MiB: a sample, not a peak or project attribution. No GPU job or paid
service was introduced. Existing real-browser seeded-token evidence is not end-user login evidence.

Next: accessible login/logout UI, reviewed same-origin hosting, and real-browser acceptance with
user-entered credentials, permission rejection and logout. AAOS/deployment gates remain pending.
