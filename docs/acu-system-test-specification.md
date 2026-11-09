# ACU System Test Specification

This specification describes how the virtual airbag control unit is verified at system level:
the common preconditions, the test design technique used for each area, and where every test
case is defined. The test plan is [acu-system-test-plan.md](acu-system-test-plan.md); the full
list of executed cases with verdicts is written to `test-catalogue.md` on every run.

## 1. Common preconditions

Unless a case says otherwise, each test case starts on a fresh bench:

1. Supply at 12.0 V (`PSU VOLT 12.0`, `OUTP ON`), KL15 closed (`REL ROUT:CLOS (@1)`).
2. Self-test finished: `acu_status.SystemState` = NORMAL (2), warning lamp off.
3. All squib loops at the nominal 2.2 Ω (`FIB ROUT:CLOS (@1:4)`), 25 °C, driver buckled,
   passenger seat empty, passenger airbag enabled.
4. Vehicle-status sender at 50 km/h every 100 ms; no stored DTC.

A test case passes when every check passes. Checks compare an expected value or a limit with
the observed value; both are recorded in the report.

## 2. Test design by area

| Area | Technique | Test cases | Requirements |
|---|---|---|---|
| Self-test and warning lamp | State transitions (OFF → SELF_TEST → NORMAL), timing | ACU-T01, TT-ACU-004, TU-ACU-001 | BENCH-F-024 |
| Squib loop monitoring | Boundary values (1.4 / 1.5 / 5.0 / 5.1 Ω), equivalence classes (short, open, in range) | TT-ACU-001[1-5], HIL-T10, ACU-T02, ACU-T03 | BENCH-F-025, BENCH-F-040 |
| Loop shorts | Fault injection (short to ground, short to battery) | HIL-T09 | BENCH-F-040 |
| DTC lifecycle | State transitions of the status byte (pending, confirmed, healed, cleared) | ACU-T02, ACU-T03, ACU-T14, TU-ACU-003 | BENCH-F-026 |
| Supply range | Equivalence classes and boundaries (8.5 / 13.5 / 17 V), timing of debounce | ACU-T04, HIL-T03 | BENCH-F-027, BENCH-F-043 |
| Supply profiles | ISO 16750-2-style profiles, negative tests | HIL-T04 to HIL-T08 | BENCH-F-038, BENCH-F-043 |
| Deployment decision | Decision table (occupancy × airbag switch × buckle), severity classes | TT-ACU-002[1-4], ACU-T07 to ACU-T09 | BENCH-F-029 |
| Misuse immunity | Negative test with a valid precondition (main-sensor delta-v above the threshold) | ACU-T06 | BENCH-F-030 |
| Energy reserve | Fault injection in time (supply loss before and during a crash) | ACU-T10, ACU-T11, HIL-T04, HIL-T05 | BENCH-F-031 |
| Crash output | Timing measurement, E2E checks, one-shot behaviour | ACU-T08, ACU-T15, TU-ACU-004 | BENCH-F-032 |
| Failed loops in a crash | Fault injection combined with a crash | ACU-T12 | BENCH-F-033 |
| Communication supervision | Timeout tests, restbus interruption | ACU-T05, EMC-T06 | BENCH-F-028, BENCH-F-049 |
| E2E protection | Continuity over every frame | TU-ACU-002, ACU-T01 | BENCH-F-020 |
| Diagnostics | Positive and negative responses, sessions, DIDs | TT-ACU-003, TU-ACU-005, HIL-T11 | BENCH-F-018, BENCH-F-034 |
| Temperature | Extremes (-40 / +85 °C), drift of a marginal loop, over-temperature | HIL-T12, HIL-T13 | BENCH-F-042 |
| Firing current | Measurement on the supply | HIL-T14 | BENCH-F-037, BENCH-F-043 |
| Instrument interface | Positive and negative SCPI tests | HIL-T01, HIL-T15 | BENCH-F-036, BENCH-F-039 |
| Transient immunity | Required functional status class per pulse, no-deployment check | EMC-T01 to EMC-T07 | BENCH-F-045 to BENCH-F-048, BENCH-NF-015 |

## 3. Where test cases are defined

| Definition | Kind | Cases |
|---|---|---|
| `tools/run_test_units_demo.py` (`unit`) | Event-driven test unit (Python, CAPL-like) | TU-ACU-001 to TU-ACU-005 |
| `tools/test_tables/acu_system_tests.json` | JSON test table with parameters | TT-ACU-001[1-5], TT-ACU-002[1-4], TT-ACU-003, TT-ACU-004 |
| `tools/run_airbag_bench_demo.py` | ACU campaign | ACU-T01 to ACU-T15 |
| `tools/run_hil_bench_demo.py` | HiL campaign | HIL-T01 to HIL-T15 |
| `tools/run_emc_bench_demo.py` | EMC-concept campaign | EMC-T01 to EMC-T07 |

53 test cases in total. Requirements verified only at unit level are listed as *unit tests only*
in `coverage.md`; they are covered by `tests/test_bench_*.py` and do not need a system test case.

## 4. Example test case

**TT-ACU-002[3] Severe crash, passenger seat empty, driver buckled** (BENCH-F-029)

| Step | Action | Expected |
|---|---|---|
| 1 | Common preconditions | NORMAL, lamp off |
| 2 | Occupancy: passenger empty, airbag enabled, driver buckled | - |
| 3 | Crash pulse: 30 g half sine, 60 ms, starting after 10 ms | - |
| 4 | Wait 300 ms | - |
| 5 | Read fired loops | driver airbag, driver pretensioner only |
| 6 | Wait for `acu_status.CrashStored` = 1 | within 150 ms |
