# Volume VIII Test Framework Roadmap

- [x] **VIII-1 Test catalog** - reusable test definitions, structured steps, versioned lifecycle,
  deterministic suite composition, RBAC, audit, events, APIs, and workbook baseline.
- [x] **VIII-2 Execution binding** - active suite snapshots, materialized run cases, bounded results,
  deterministic aggregation, RBAC, audit, outbox, and live updates.
- [x] **VIII-3 Scheduler and selection** - durable scheduled execution with immutable smoke, sanity,
  and regression suite-selection snapshots.
- [ ] **VIII-4 Performance and stress** - deferred until near project completion, when stable baselines
  can support load profiles, thresholds, resource budgets, and comparable trend evidence.
- [x] **VIII-5 Fault injection** - reusable, bounded fault campaigns across vehicle, ECU, CAN,
  diagnostics, EV, and ADAS, with recovery plans and versioned evidence.
- [ ] **VIII-6 Mutation testing and coverage** - mutation operators, kill rate, requirement coverage, and gaps.
- [ ] **VIII-7 Cross-platform automation** - Gateway and CarSystemUI orchestration, reporting, and workbook completion.

## Next recommended increment

VIII-6 should add mutation operators, mutation campaigns, kill-rate evidence, requirement coverage,
and explicit gap analysis. VIII-4 remains planned but intentionally deferred until near completion
to avoid expensive measurements against an unstable platform baseline.
