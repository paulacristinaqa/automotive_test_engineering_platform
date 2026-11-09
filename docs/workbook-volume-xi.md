# ATEP Volume XI Virtual Test Bench Engineering Workbook

Version 1.0.0 completes Volume XI (XI-1 to XI-7). XI-1 delivers Vector-compatible DBC, ASC and BLF
artifacts and a python-can bench bus. XI-2 adds ISO-TP, a UDS tester with P2/P2* timing, a
virtual ECU, cyclic message supervision and E2E protection, all running on logical time. XI-3
adds a virtual airbag control unit as the device under test, with a 15-case system-test
campaign. XI-4 adds SCPI bench instruments (supply with voltage profiles, KL15 relay, fault box,
multimeter, climate chamber) and a 15-case HiL campaign. XI-5 adds a transient generator, ACU
input protection, CAN error frames with bus-off, functional status classification and an
EMC-concept campaign. XI-6 adds vTESTstudio-style test units and JSON test tables, CANoe-style,
JUnit, HTML and traceability reports, and a requirement coverage matrix. XI-7 delivers the ACU
system test: plan, specification, exit criteria, release recommendation, defect drafts and an
evidence manifest.

## Scope and architecture

The `atep.bench` package sits beside the CAN network domain and only reads its data. Pure
renderers turn a network specification into DBC text and a list of trace frames into ASC text or
BLF bytes. A thin export service loads the network, its optional DBC catalogue, ECU names and
submitted frames. Two read-only endpoints serve the files under
`/vehicles/{vehicle_id}/can-networks/exports`.

The bench bus wraps python-can behind an interface allowlist. The XI-1 demo encodes cyclic
traffic with the ATEP codec, sends it on the bus, receives it on a second node and decodes it with
cantools, an implementation independent of ATEP.

XI-2 protocols are sans-IO bench nodes: `on_frame`, `poll` and `next_deadline_us`, all on logical
microseconds. `SimulatedLink` runs nodes on a deterministic shared bus with frame times derived
from the bitrates. `BusNodeRunner` runs the same nodes on a python-can bus with the wall clock.
Architecture details are in [virtual-bench.md](virtual-bench.md).

## Engineering decisions

### XI-1

- Write ASC and DBC with ATEP code. The python-can ASC writer stamps the host clock and local time
  zone into the header, which would make exports irreproducible.
- Write BLF with the python-can writer, with a start marker that pins the file start to the
  network creation time. Its output is reproducible for identical input.
- Anchor traces to the network creation time in UTC, truncated to the millisecond BLF can store.
- Keep python-can as a runtime dependency, because the API writes BLF. Keep cantools as a
  development dependency, used only to check ATEP output.
- Reject DBC names that collide after conversion instead of renaming them silently.
- Name ECUs without a record `ECU_<uuid hex>` so fallback names never collide.
- Bound trace exports to 10,000 frames and page with `after_sequence`, using a `limit + 1` read
  instead of a count query.
- Allow only `virtual`, `socketcan`, `vector`, `pcan` and `slcan` interfaces. CI uses `virtual`.

### XI-2

- Implement ISO-TP and UDS in ATEP instead of adding python-can-isotp or udsoncan. The bench
  needs every timer and error to be visible and testable on logical time, and the code doubles as
  study material.
- Keep protocol logic sans-IO. Timing bugs are reproduced by stepping a simulated link, not by
  sleeping in tests.
- Report transport problems as events, so a tester can classify them as test results.
- Restrict the suppress-positive-response bit to services with a sub-function. A test caught the
  tester treating `22 F1 90` as suppressed because `0xF1` has bit 7 set.
- Make the simulated link raise after a bounded number of steps when a node keeps a stale
  deadline, instead of hanging a test run.
- Verify the CRC against the published check value and the independent crccheck library.

### XI-3

- Model an airbag control unit because it is the product family of the target role and exercises
  every XI-1 and XI-2 building block: DBC-encoded frames, E2E, supervision and UDS.
- Encode ACU frames with the ATEP DBC codec from the same specification that is exported, so the
  trace and the DBC can never disagree.
- Reuse the XI-2 virtual ECU for diagnostics through three overridable hooks (`read_data`,
  `dtc_records`, `clear_dtcs`) instead of a second UDS server.
- Treat DTC memory as non-volatile and runtime state (debounce timers, supervision, session) as
  volatile across power cycles.
- Mark a fired squib as an open circuit and stop monitoring it, so a deployment does not raise
  loop DTCs.
- Prove the campaign can fail: two tests run it against a miscalibrated ACU and an ACU without
  safing. They exposed two weaknesses in the first draft of the campaign: a case that crashed
  instead of failing, and a hammer blow too weak to need the safing sensor.

### XI-4

- Drive instruments with SCPI strings, not Python calls, so test scripts read like the scripts
  of a real HiL rack and SCPI mistakes are tested too.
- Keep instrument errors in a `SYST:ERR?` queue instead of raising, as real instruments do.
- Run voltage profiles and temperature ramps as bench nodes on logical time, so a 25 s profile
  costs milliseconds and stays deterministic.
- Debounce supply DTCs for 2 s and loop DTCs for 500 ms. The HiL campaign showed that a common
  debounce would confirm an undervoltage DTC on every engine start.
- Move `Check`, `TestCase` and report writing to `atep.bench.campaign`, shared by the ACU and
  HiL campaigns and ready for XI-6.
- Findings while building XI-4: `SimulatedLink.run_until` treated its limit as absolute time, so
  every diagnostic request after 60 s of logical time silently returned the previous answer; and
  the climate chamber changed temperature at the instant of the command. Both are fixed and have
  regression tests.

### XI-5

- Treat EMC as a test-plan discipline: each exposure has a required functional status class
  and the campaign checks "this class or better" with an `at_most` check.
- Classify from observations (resets, readiness, status gaps, lost frames, DTCs, recovery)
  instead of hard-coding the expected class, so a model change shows up as a class change.
- Check "no unintended deployment" in every EMC test; any deployment is class E.
- Model CAN retransmission and bus-off instead of dropping disturbed frames. The first draft
  dropped frames after 16 attempts, which made pulse 3a look far worse than a real controller,
  and every status frame aligned with the bursts was lost.
- Latch the firing path off on a clamped input above 30 V until the next ignition cycle: a
  safe state that gives class D for the load dump by design.
- Findings while building XI-5: a long CAN burst gives a U0121 that stays pending, not
  confirmed, because the timeout lasts less than the debounce; and SCPI parameter order matters
  (`PULS:COUN 1` before a long `PULS:WIDT`), as on real generators.

### XI-6

- Keep the CAPL vocabulary (`on message`, `on timer`, wait-for-signal, test steps) so a test
  written here maps one-to-one to a vTESTstudio test unit.
- Use the worst-wins verdict rule and turn exceptions into error steps: one broken test must
  not hide the results of the others.
- Describe parameterised tests as JSON tables, so boundary values and occupancy matrices are
  data, not code, and an engineer can review or extend them without Python.
- Convert campaign results into the same test-module model, so one report and one coverage
  matrix cover every kind of test definition.
- Read coverage from the requirement document itself, and separate system-level verification
  from unit-test-only evidence.
- Findings while building XI-6: the coverage matrix exposed two traceability gaps
  (BENCH-F-039, BENCH-NF-015) between this document and the test cases; a test-table step
  written as a bare string passed validation and would only fail at run time. All are fixed
  and covered by tests.

### XI-7

- Write the test plan and specification as documents a reviewer can read, and map the plan to
  the Automotive SPICE SYS.5 base practices, because a system test is judged on its evidence as
  much as on its results.
- Identify the test object from the ACU itself (UDS DIDs) and fingerprint its calibration and
  CAN database, so a report always says exactly what was tested.
- Make the release recommendation a computed result of six exit criteria, never a manual call,
  and keep it advice to the release decision.
- Prove the campaign can block a release with seeded-defect variants, the system-level
  counterpart of the negative-campaign tests of XI-3 to XI-5.
- Findings while building XI-7: the ACU still reported the generic XI-2 software version;
  the high-threshold variant showed that a test case can fail because its own precondition
  stopped holding, which the defect-handling rules now call out for review.

## Tests and objectives

| Objective | Test |
|---|---|
| cantools parses every export and reproduces ATEP encoding and decoding | `tests/test_bench_vector_dbc.py` |
| Extended, CAN FD and BRS frames map to the right DBC IDs and attributes | `tests/test_bench_vector_dbc.py` |
| Name collisions and unknown references are rejected | `tests/test_bench_vector_dbc.py`, `tests/test_bench_exports.py` |
| ASC round-trips with exact microseconds; BLF within 1 µs | `tests/test_bench_vector_trace.py` |
| ASC does not depend on time zone or locale; BLF is reproducible | `tests/test_bench_vector_trace.py` |
| Exports need `can_networks:read`, are bounded and change nothing | `tests/test_bench_exports.py` |
| Classic, extended and FD frames cross the virtual bus without loss | `tests/test_bench_bus.py` |
| Real-time replay waits for each logical timestamp; deterministic replay never sleeps | `tests/test_bench_bus.py` |
| The XI-1 demo passes end to end and writes identical files on every run | `tests/test_bench_demo.py` |
| ISO-TP segmentation, flow control, STmin, sequence wrap, CAN FD and every error case | `tests/test_bench_isotp.py` |
| P2, P2*, response pending, suppressed responses and every client outcome | `tests/test_bench_uds.py` |
| Virtual ECU sessions, S3, security lockout, DIDs, DTCs and reset | `tests/test_bench_uds.py` |
| CRC check value, counter wrap, every E2E status and timeout supervision | `tests/test_bench_e2e_supervision.py` |
| Bus serialization, frame times, stale-deadline guard and python-can runner | `tests/test_bench_link.py` |
| The XI-2 demo passes on the simulated link and on a python-can bus | `tests/test_bench_ecu_demo.py` |
| DTC encoding, crash pulses, power cycles, energy reserve, DIDs, DBC decoding of ACU frames | `tests/test_bench_airbag.py` |
| The 15-case ACU campaign passes, is reproducible and fails on defective ACUs | `tests/test_bench_airbag_demo.py` |
| SCPI parsing, channel lists, parameters, common commands and the error queue | `tests/test_bench_scpi.py` |
| Profiles, supply, relay, fault box, multimeter, chamber, current model, shorts and drift | `tests/test_bench_instruments.py` |
| The 15-case HiL campaign passes, is reproducible and fails on four kinds of defective ACU | `tests/test_bench_hil_demo.py` |
| FSC classification, pulses, input protection, firing inhibit, error frames, bus-off, TRG SCPI | `tests/test_bench_emc.py` |
| The 7-case EMC campaign passes, is reproducible and fails on three kinds of defective ACU | `tests/test_bench_emc_demo.py` |
| Verdict rules, checks, waits, handlers, diagnostics, fresh benches, campaign conversion | `tests/test_bench_testunit.py` |
| Placeholders, parameter expansion, validation messages, shipped table | `tests/test_bench_testtable.py` |
| XML, JUnit, HTML, CSV and coverage outputs; determinism | `tests/test_bench_reports.py` |
| 53 cases from five modules pass; no requirement uncovered or undefined | `tests/test_bench_test_units_demo.py` |
| Exit criteria, defect drafts, identification, release recommendation, seeded defects, manifest | `tests/test_bench_system_test.py` |

## Risks and technical debt

- The bench has no electrical layer. Bench instruments and transients arrive in XI-4 and XI-5,
  as models, not measurements.
- Arbitration batches and multi-bus campaigns are not yet exported as traces.
- The DBC export does not write value tables (`VAL_`) or multiplexed signals, because ATEP does
  not model them yet.
- The Vector import of the generated files is checked with python-can and cantools, not with
  CANoe itself. Open the demo files in CANoe or CANalyzer to confirm.
- ISO-TP stops at 4,095 bytes and does not model functional addressing.
- On a python-can bus the wall clock drives P2; a heavily loaded CI runner could make the bus
  demo test slower. The simulated link has no such risk.
- The virtual ECU and the ACU keep their own in-memory state and are not connected to the ATEP
  diagnostics domain in PostgreSQL. The bench is meant to run standalone; a bridge can come with
  XI-7 if campaign evidence must be stored by the platform.
- The XML report mirrors the structure of a CANoe report but is not a byte-compatible CANoe
  file; test tables run on this bench, not in vTESTstudio.
- EMC results are behavioural: no coupling physics and no emission or immunity measurement.
- Instruments have no noise, accuracy class, settling time or current limit; profiles are
  shortened ISO 16750-2 shapes, not certified levels.
- The ACU model is illustrative: one frontal axis, no side or rollover sensing, no occupant
  classification, simplified squib timing and no firing current.

## XI-1 outcome

XI-1 is complete. `tools/run_virtual_bench_demo.py` sends 160 frames per second of reference
traffic on the virtual bus with no payload, encoding or decoding mismatch.

## XI-2 outcome

XI-2 is complete. `tools/run_ecu_communication_demo.py` passes all 19 diagnostic steps, the E2E
fault sequence and the timeout supervision sequence on the simulated link, and 18 diagnostic steps
on a python-can virtual bus (the S3 step needs a 6 s wait and only runs simulated).

## XI-3 outcome

XI-3 is complete. `tools/run_airbag_bench_demo.py` passes 15 system-test cases traced to
BENCH-F-024 to BENCH-F-034, writes a JSON and Markdown report, the ACU DBC and Vector traces of
the severe crash, and produces identical files on every run.

## XI-4 outcome

XI-4 is complete. `tools/run_hil_bench_demo.py` passes 15 HiL cases traced to BENCH-F-036 to
BENCH-F-043 using only SCPI instruments and UDS, and writes reports and a timestamped SCPI log.

## XI-5 outcome

XI-5 is complete. `tools/run_emc_bench_demo.py` meets the required functional status class in
all 7 tests without any deployment, writes an EMC test plan with achieved classes, and a trace
whose error frames show in CANoe.

## XI-6 outcome

XI-6 is complete. `tools/run_test_units_demo.py` runs 53 test cases from an event-driven test
unit, a JSON test table and the three campaigns, all passing, and writes CANoe-style XML,
JUnit, HTML, traceability CSV and a coverage matrix with no requirement left uncovered.

## XI-7 outcome

XI-7 is complete. `tools/run_acu_system_test.py` runs 53 test cases on the baseline ACU, meets all
six exit criteria and recommends the release; each of the three seeded-defect variants is
rejected with its defects drafted.

## Volume XI outcome

Volume XI is complete. The virtual bench covers the path from CAN artifacts (XI-1) and ECU
communication (XI-2) to a device under test (XI-3), HiL instruments (XI-4), transient concepts
(XI-5), test authoring and traceability (XI-6) and a system test with a release recommendation
(XI-7). The next planned volume is Volume XII DevOps.
