# Volume VIII Test Framework Roadmap

- [x] **VIII-1 Test catalog** - reusable test definitions, structured steps, versioned lifecycle,
  deterministic suite composition, RBAC, audit, events, APIs, and workbook baseline.
- [ ] **VIII-2 Execution binding** - create test runs from active suite snapshots and record case results.
- [ ] **VIII-3 Scheduler and selection** - scheduled execution, smoke, sanity, and regression selection.
- [ ] **VIII-4 Performance and stress** - load profiles, thresholds, resource budgets, and trend evidence.
- [ ] **VIII-5 Fault injection** - reusable fault campaigns across vehicle, ECU, CAN, diagnostics, EV, and ADAS.
- [ ] **VIII-6 Mutation testing and coverage** - mutation operators, kill rate, requirement coverage, and gaps.
- [ ] **VIII-7 Cross-platform automation** - Gateway and CarSystemUI orchestration, reporting, and workbook completion.

## Next recommended increment

VIII-2 should bind an active suite snapshot to a test run and introduce deterministic per-case
execution records, results, evidence references, and aggregate run status.
