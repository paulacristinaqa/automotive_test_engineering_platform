# Volume VIII Test Framework Roadmap

- [x] **VIII-1 Test catalog** - reusable test definitions, structured steps, versioned lifecycle,
  deterministic suite composition, RBAC, audit, events, APIs, and workbook baseline.
- [x] **VIII-2 Execution binding** - active suite snapshots, materialized run cases, bounded results,
  deterministic aggregation, RBAC, audit, outbox, and live updates.
- [x] **VIII-3 Scheduler and selection** - durable scheduled execution with immutable smoke, sanity,
  and regression suite-selection snapshots.
- [x] **VIII-4 Performance and stress** - bounded load profiles, explicit resource limits,
  threshold evaluation, immutable evidence, and comparable historical baselines.
- [x] **VIII-5 Fault injection** - reusable, bounded fault campaigns across vehicle, ECU, CAN,
  diagnostics, EV, and ADAS, with recovery plans and versioned evidence.
- [x] **VIII-6 Mutation testing and coverage** - bounded mutation operators, immutable campaign
  snapshots, deterministic kill rate, requirement traceability, and explicit coverage gaps.
- [x] **VIII-7 Cross-platform automation** - correlated Gateway and CarSystemUI evidence,
  terminal orchestration validation, deterministic reporting, RBAC, audit, events, and workbook completion.

## Volume status

The complete Volume VIII baseline is implemented. Performance and stress execution remains isolated
from the API and bounded by profile resource budgets; hosted CI is preferred for meaningful loads.
