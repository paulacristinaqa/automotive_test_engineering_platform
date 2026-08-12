# Volume II delivery roadmap — Digital Vehicle

## Delivery principle

Build one deterministic vehicle domain before adding protocol and physics complexity. Each slice
must preserve public API isolation, explicit units and bounds, atomic evidence, repeatable tests,
and compatibility with the future Android Automotive gateway.

| Increment | Scope | Status | Completion evidence |
|---|---|---|---|
| II-1 | Versioned state aggregate, safe baseline, RBAC, invariants, audit, and outbox | Implemented | Unit, contract, RBAC, migration, and integration tests |
| II-2 | Deterministic simulation clock and command-driven state transitions | Implemented | Repeatable time-step, state-machine, retry, and evidence tests without wall-clock dependence |
| II-3 | Sensors and actuator models with noise, calibration, and fault modes | Implemented | Seeded simulations and boundary/fault tests |
| II-4 | Thermal, battery-energy, powertrain, braking, steering, suspension, and lighting behavior | Implemented | Coupled drive-corner-brake and conservation/bounds tests |
| II-5 | Multi-vehicle simulation sessions and reproducible snapshots | Planned | Isolation, scale, reset, and replay tests |
| II-6 | Vehicle Gateway mapping to Android Automotive/VHAL contracts | Planned | Contract and end-to-end CarSystemUI evidence |

## Recommended next increment

Add multi-vehicle simulation sessions and reproducible snapshots. Preserve vehicle isolation,
logical-time determinism, bounded session size, reset semantics, and exact replay evidence without
introducing wall-clock loops or mandatory cloud infrastructure.
