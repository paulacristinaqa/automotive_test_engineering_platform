# ATEP Volume XI Virtual Test Bench Engineering Workbook

Version 0.3.0 completes XI-1 to XI-3. XI-1 delivers Vector-compatible DBC, ASC and BLF
artifacts and a python-can bench bus. XI-2 adds ISO-TP, a UDS tester with P2/P2* timing, a
virtual ECU, cyclic message supervision and E2E protection, all running on logical time. XI-3
adds a virtual airbag control unit as the device under test, with a 15-case system-test
campaign.

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

## Next increment

XI-4 Bench instruments: a programmable power supply with ISO 16750-2-style profiles and a
fault-injection box driving the ACU through SCPI-style commands.
