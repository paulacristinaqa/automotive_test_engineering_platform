# Volume X Dashboard Roadmap

The dashboard is delivered as a sequence of read-only contracts before an interactive client is
introduced. This keeps source domains authoritative and makes every visualization testable.

| Increment | Scope | Status |
|---|---|---|
| X-1 | Overview contract, KPI aggregation, evidence cards, RBAC, and safe limits | Complete |
| X-2 | Test quality trends, regression history, and failure drill-down | Complete |
| X-3 | Vehicle, ECU, CAN, and diagnostics operational views | Complete |
| X-4 | EV, charging, thermal, and ADAS visual analytics | Complete |
| X-5 | Supporting evidence and explicit OTA/cybersecurity/standards gaps (approved reduced scope) | Complete within approved scope |
| X-6 | Live updates, exports, retention, and performance hardening | Backend scope complete — X-6.7 opt-in browser authentication; X-7 acceptance pending |
| X-7 | Cross-platform dashboard validation and Volume X completion | In progress — X-7.10 Android engineering panel implemented; actual AAOS/deployment gates pending |

## Next increment

X-6.1 implements transient exports; X-6.2 adds periodic snapshots; X-6.3 verifies query reduction,
metric equivalence and database read-only behavior, with retained non-sensitive test evidence.
X-6.4 adds distinct populated temporary components while retaining the empty-state profile.
X-6.5 bounds admission before authentication and adds a shared Redis handshake budget.
X-6.6 enforces the native-only Origin boundary and verifies quota/expiry with independent Redis pools.
X-6.7 adds a separate, disabled-by-default browser route with exact origins and first-message JWT.
The next increment is X-7 cross-platform acceptance, as defined in `dashboard-acceptance.md`.
X-7.1 evidence is recorded in `dashboard-browser-acceptance.md`; X-7.2 client lifecycle and
reconnect/staleness evidence is in `dashboard-client-lifecycle.md`. X-7.4 adds end-user login;
broader product UI, AAOS and deployment gates remain pending.
X-7.3 adds the unit-tested session controller in `dashboard-client-session.md`.
X-7.4 adds the same-origin login/logout shell and real form-login/no-role evidence in
`dashboard-login-ui.md`. X-7.5 records real-shell local expiration, permission loss, controlled
reconnect and basic keyboard acceptance in `dashboard-shell-lifecycle.md`.
X-7.6 responsive and additional keyboard/markup evidence is in `dashboard-responsive-accessibility.md`.
X-7.7 introduces the native request foundation in the companion Android repository;
see `dashboard-aaos-prerequisites.md`. Next are native lifecycle/presentation and actual
AAOS acceptance, followed by trusted-proxy deployment acceptance. Request unit tests
alone do not complete the AAOS gate. X-7.8 adds the isolated lifecycle state machine
described in `dashboard-native-lifecycle.md`; the transport/parser adapter and
presentation remain prerequisites to device acceptance.
X-7.9 adds the OkHttp/envelope adapter (`dashboard-native-transport.md`) with fake
transport tests. Next is Android presentation/session ownership, followed by live
backend/AAOS acceptance; JVM adapter tests do not pass that gate.
X-7.10 wires an engineering Compose panel and session ownership; see
`dashboard-android-panel.md`. The next gate is actual backend/AAOS interaction and
visual/lifecycle acceptance, not another claim based only on compilation.
X-7.11 passes the basic real AAOS LIVE/token-clearing/background-return smoke;
see `dashboard-aaos-acceptance.md`. Initial no-role denial also passed on device.
X-7.12 also passes active-session permission loss after a real device LIVE
checkpoint (`dashboard-aaos-permission-loss.md`). X-7.13 passes local expiry
with a still-valid server token (`dashboard-aaos-local-expiry.md`); X-7.14 passes
natural server JWT expiration (`dashboard-aaos-server-expiry.md`).
X-7.15 passes inactive-user handling (`dashboard-aaos-inactive-user.md`).
X-7.16 passes controlled TCP stall/interruption, stale retention and delayed
reconnect on actual AAOS (`dashboard-aaos-network-recovery.md`). One successful
device run follows an unclassified initial failure; repeatability is not implied.
X-7.17 passes local expiry during real reconnect backoff, including route
recovery without automatic restart (`dashboard-aaos-retry-expiry.md`).
X-7.18 passes actual-device retry exhaustion (`dashboard-aaos-retry-exhaustion.md`).
X-7.19 normal ten-snapshot completion passed after explicitly refreshing the
accessibility preview node: sequence 10, retained stale evidence, empty token
input and no automatic restart on one connection. Earlier failed attempts are
preserved in `dashboard-aaos-normal-completion.md`. X-7.20 passes the first
trusted-proxy deployment slice: exact forwarding trust and spoof-resistant
Redis handshake admission through local Nginx (`dashboard-proxy-boundary.md`).
X-7.21 passes local TLS/certificate validation and API host-port isolation
(`dashboard-proxy-tls.md`). X-7.22 passes bounded shared-admission validation with
two independent single-worker replicas (`dashboard-multiprocess-admission.md`),
without a stress, automatic-balancing or production-capacity claim. X-7.23 passes
live local certificate lifecycle acceptance: an explicitly trusted expired certificate
fails with verification code 10, and a restart-based replacement recovers verified
HTTPS/WSS (`dashboard-certificate-lifecycle.md`). The complete deployment
gate, broader accessibility and device/browser matrix remain open.
The broader Android gate is not yet complete.
Screen-reader/contrast/browser-matrix checks and real network partitions
remain explicit evidence gaps rather than implied passes.
Actual client/deployment evidence remains a release gate; protocol tests do not establish it.
Small-fixture timings are not capacity guarantees.

X-5 was explicitly reduced to supporting evidence and gap reporting. OTA lifecycle views and
formal ASPICE/ISO 26262/cybersecurity mappings remain deferred dependencies, not delivered features.
