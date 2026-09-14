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
| X-7 | Cross-platform dashboard validation and Volume X completion | In progress — X-7.2 reusable browser lifecycle client validated |

## Next increment

X-6.1 implements transient exports; X-6.2 adds periodic snapshots; X-6.3 verifies query reduction,
metric equivalence and database read-only behavior, with retained non-sensitive test evidence.
X-6.4 adds distinct populated temporary components while retaining the empty-state profile.
X-6.5 bounds admission before authentication and adds a shared Redis handshake budget.
X-6.6 enforces the native-only Origin boundary and verifies quota/expiry with independent Redis pools.
X-6.7 adds a separate, disabled-by-default browser route with exact origins and first-message JWT.
The next increment is X-7 cross-platform acceptance, as defined in `dashboard-acceptance.md`.
X-7.1 evidence is recorded in `dashboard-browser-acceptance.md`; X-7.2 client lifecycle and
reconnect/staleness evidence is in `dashboard-client-lifecycle.md`. End-user login/product UI,
AAOS and deployment gates remain pending.
Actual client/deployment evidence remains a release gate; protocol tests do not establish it.
Small-fixture timings are not capacity guarantees.

X-5 was explicitly reduced to supporting evidence and gap reporting. OTA lifecycle views and
formal ASPICE/ISO 26262/cybersecurity mappings remain deferred dependencies, not delivered features.
