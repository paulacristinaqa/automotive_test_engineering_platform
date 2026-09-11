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
| X-6 | Live updates, exports, retention, and performance hardening | In progress — X-6.1 bounded transient exports |
| X-7 | Cross-platform dashboard validation and Volume X completion | Planned |

## Next increment

X-6.1 implements bounded transient JSON exports. X-6.2 should address authenticated live updates
and freshness; subsequent X-6 work must measure query costs and complete retention/performance
policy validation. Do not mark X-6 complete until these remaining capabilities are verified.

X-5 was explicitly reduced to supporting evidence and gap reporting. OTA lifecycle views and
formal ASPICE/ISO 26262/cybersecurity mappings remain deferred dependencies, not delivered features.
