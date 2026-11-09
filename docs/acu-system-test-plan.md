# ACU System Test Plan

| Item | Value |
|---|---|
| Document | ACU system test plan, Volume XI-7 |
| Test object | Virtual airbag control unit (`atep.bench.airbag`), software `ACU-SW-1.0.0` |
| Test level | System test (verification of the integrated ECU against its system requirements) |
| Test basis | [requirements-volume-xi.md](requirements-volume-xi.md) |
| Test specification | [acu-system-test-specification.md](acu-system-test-specification.md) |
| Execution | `python tools/run_acu_system_test.py --output out/acu-system-test` |

The ACU is a teaching model on a virtual bench. This plan is written the way a system test plan
for a real airbag ECU would be, so its structure, criteria and evidence can be discussed and
reused; thresholds and test levels are illustrative.

## 1. Scope

In scope: deployment decision, squib loop monitoring, warning lamp and self-test, supply and
energy reserve behaviour, DTC lifecycle, diagnostics (UDS over ISO-TP), CAN outputs with E2E
protection, supervision of received messages, HiL instrument interfaces, transient immunity
(conceptual) and requirement traceability.

Out of scope: real hardware, analog and electrical timing, radiated or conducted EMC
measurement, side and rollover sensing, occupant classification, flashing and production
end-of-line tests.

## 2. Test object and variants

The test object is identified in every summary report by the ACU's own diagnostic DIDs
(F195 software version, F190 VIN) and by SHA-256 fingerprints of its calibration and CAN
database. Seeded-defect variants exist only to prove that the campaign detects regressions:

| Variant | Purpose | Expected recommendation |
|---|---|---|
| `baseline` | Release candidate | Release recommended |
| `short-supply-debounce` | Supply DTC debounce 500 ms instead of 2 s | Not recommended |
| `no-firing-inhibit` | Firing inhibit level above the 33 V input clamp | Not recommended (safety) |
| `high-airbag-threshold` | Airbag threshold 30 km/h instead of 14 km/h | Not recommended (safety) |

## 3. Test strategy

| Level | Where | What |
|---|---|---|
| Unit and component | `pytest` (`tests/test_bench_*.py`) | Protocol logic, models, instruments, reports; every commit in CI |
| System | Virtual bench (`tools/run_acu_system_test.py`) | The integrated ACU through CAN, UDS and SCPI instruments only |

System test cases treat the ACU as a black box: stimuli come from bench instruments, the
vehicle-status sender and crash pulses; observations come from CAN frames, UDS responses and
instrument readings. Internal ACU attributes are read only where a real bench would measure the
same quantity (for example the lamp, which a bench reads from the lamp driver).

Test design techniques are listed per area in the test specification: equivalence classes,
boundary values, state transitions, decision tables, fault injection, timing measurement and
negative testing.

The whole system test is automated and deterministic. Regression strategy: the full system test
runs on every change of the ACU model, calibration or CAN database, because a run takes seconds
of wall time.

## 4. Test environment

| Element | Identification |
|---|---|
| Programmable supply | `PSU` (KL30, ISO 16750-2-style profiles) |
| Relay card | `REL` (KL15) |
| Fault-injection box | `FIB` (squib loops 1-4) |
| Multimeter | `DMM` |
| Climate chamber | `CHAM` |
| Transient generator | `TRG` (ISO 7637-2-style pulses) |
| Bus | Simulated classic CAN at 500 kbit/s on logical time |
| Restbus | Vehicle-status sender (VCU stand-in), UDS tester |

The summary report records every instrument's `*IDN?` answer and the Python and python-can
versions.

## 5. Entry criteria

- The test object identifies itself over UDS (DIDs F195 and F190).
- The requirements document and the test specification are under version control.
- The unit and component tests pass in CI.

## 6. Exit criteria and release recommendation

| ID | Criterion |
|---|---|
| EC-1 | Every test case executed to a verdict: no error, no inconclusive |
| EC-2 | Every test case passed |
| EC-3 | Every requirement verified by a passing system test or by unit tests; none failed or uncovered |
| EC-4 | Every test case of a safety-related requirement passed |
| EC-5 | No unintended deployment in any EMC test |
| EC-6 | Every EMC test reached its required functional status class |

A release is recommended only when all six criteria are met. The recommendation is advice to the
release decision, not the decision itself.

Safety-related requirements: BENCH-F-029 (deployment decision), BENCH-F-030 (misuse immunity),
BENCH-F-031 (energy reserve), BENCH-F-032 (crash output and one-shot deployment), BENCH-F-033
(failed loops), BENCH-F-046 (input protection and firing inhibit) and BENCH-NF-015 (no deployment
in EMC tests).

## 7. Defect handling

Every test case that does not pass produces a defect draft (`DEF-nnn`) in the summary report
with the failing steps, expected and actual values and the requirements it traces to. Severity
is *High (safety-related)* when the case traces to a safety-related requirement, otherwise
*Medium*. A test case that fails because its own precondition no longer holds (for example the
hammer-blow case when the airbag threshold changes) is reported the same way and must be
reviewed: the defect may be in the test, not in the ACU.

## 8. Risks

| Risk | Mitigation |
|---|---|
| The model hides behaviour a real ECU shows | State model limits in every report; keep thresholds explicit in `AcuCalibration` |
| Tests pass because they cannot fail | Seeded-defect variants and negative-campaign tests prove each campaign can fail |
| Requirements and tests drift apart | Coverage matrix from the requirements document; a test fails on undefined or uncovered requirements |
| Timing-dependent flakiness | Logical time on a simulated bus; identical evidence on every run |

## 9. Deliverables

| File | Content |
|---|---|
| `test-summary-report.md` / `test-summary.json` | Test object, environment, results, exit criteria, recommendation, defects |
| `test-catalogue.md` | Every executed test case with its requirements and verdict |
| `test-report.xml`, `junit.xml`, `report.html` | Detailed results (CANoe-style XML, CI, people) |
| `traceability.csv`, `coverage.md` | Requirement traceability and coverage |
| `evidence/` | Campaign artifacts: DBC, ASC/BLF traces, SCPI log, EMC test plan |
| `evidence-manifest.json` | SHA-256 of every file above |

## 10. Mapping to Automotive SPICE SYS.5

Paraphrased base practices of SYS.5 System Verification (Automotive SPICE 4.0):

| Base practice | Where it is met |
|---|---|
| Specify verification measures for the system | Test specification, test cases with requirements, expected values and pass criteria |
| Select verification measures, including regression | Section 3; the full run is the regression set |
| Perform verification of the integrated system | `tools/run_acu_system_test.py` on the virtual bench |
| Ensure consistency and bidirectional traceability | `traceability.csv`, `coverage.md`, regression test on undefined requirements |
| Summarize and communicate results | `test-summary-report.md` with exit criteria, recommendation and defects |
