# Volume VIII Test Framework Roadmap

- [x] **VIII-1 Test catalog** - reusable test definitions, structured steps, versioned lifecycle,
  deterministic suite composition, RBAC, audit, events, APIs, and workbook baseline.
- [x] **VIII-2 Execution binding** - active suite snapshots, materialized run cases, bounded results,
  deterministic aggregation, RBAC, audit, outbox, and live updates.
- [ ] **VIII-3 Scheduler and selection** - scheduled execution, smoke, sanity, and regression selection.
- [ ] **VIII-4 Performance and stress** - load profiles, thresholds, resource budgets, and trend evidence.
- [ ] **VIII-5 Fault injection** - reusable fault campaigns across vehicle, ECU, CAN, diagnostics, EV, and ADAS.
- [ ] **VIII-6 Mutation testing and coverage** - mutation operators, kill rate, requirement coverage, and gaps.
- [ ] **VIII-7 Cross-platform automation** - Gateway and CarSystemUI orchestration, reporting, and workbook completion.

## Next recommended increment

VIII-3 should extend the durable scheduler with catalog-suite selection policies for smoke, sanity,
and regression execution while preserving the VIII-2 execution snapshot.
