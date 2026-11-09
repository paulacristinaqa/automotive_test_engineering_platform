# Volume XI Virtual Test Bench Requirements

Volume XI brings ATEP closer to a system-test bench: Vector-compatible artifacts, a real CAN
software stack, a virtual device under test, simulated bench instruments, and vTESTstudio-style
test authoring. It does not replace a hardware bench; see the limits at the end.

## XI-1 Real CAN stack and Vector artifacts

### Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-F-001 | Export a CAN network and its optional DBC catalogue as a DBC file with `BusType`, `DBName`, `Baudrate` and, for CAN FD networks, `BaudrateCANFD` attributes. | `tests/test_bench_vector_dbc.py` |
| BENCH-F-002 | Map standard, extended and CAN FD frame contracts to `BO_` identifiers (bit 31 set for extended IDs), `VFrameFormat` and `CANFD_BRS` attributes. | `tests/test_bench_vector_dbc.py` |
| BENCH-F-003 | Export each signal's start bit, length, byte order, signedness, factor, offset, unit, receivers and physical range; derive the range from the raw range when none is declared. | `tests/test_bench_vector_dbc.py` |
| BENCH-F-004 | Convert ATEP identifiers to DBC identifiers and reject two names that collide after conversion with a stable contract error. | `tests/test_bench_vector_dbc.py` |
| BENCH-F-005 | Produce byte-identical DBC output for identical inputs. | `tests/test_bench_vector_dbc.py` |
| BENCH-F-006 | Export submitted frame evidence as a Vector ASC trace with classic and CAN FD lines, logical microsecond timestamps and the network creation time (UTC) as measurement start. | `tests/test_bench_vector_trace.py` |
| BENCH-F-007 | Export the same evidence as a Vector BLF trace. | `tests/test_bench_vector_trace.py` |
| BENCH-F-008 | Bound trace exports: ascending sequence order, 1 to 10,000 frames per export, `after_sequence` paging, and frame-count, last-sequence and truncation headers. | `tests/test_bench_exports.py` |
| BENCH-F-009 | Protect DBC and trace exports with `can_networks:read`; exports are read-only and change no network state. | `tests/test_bench_exports.py` |
| BENCH-F-010 | Open a bench bus only through an allowlisted python-can interface (`virtual`, `socketcan`, `vector`, `pcan`, `slcan`) and convert ATEP frames to and from python-can messages without loss. | `tests/test_bench_bus.py` |
| BENCH-F-011 | Replay frames either immediately (deterministic mode) or paced by their logical timestamps (real-time mode). | `tests/test_bench_bus.py` |
| BENCH-F-012 | Provide a virtual bench demo that sends cyclic traffic, receives it on an independent node, decodes it with an independent DBC implementation, writes `.dbc`, `.asc`, `.blf` and a JSON report, and fails on any mismatch. | `tools/run_virtual_bench_demo.py`, `tests/test_bench_demo.py` |

### Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-NF-001 | A generated DBC parsed by cantools must reproduce ATEP encoding and decoding for Intel, Motorola, signed, scaled, extended-ID and CAN FD messages. | `tests/test_bench_vector_dbc.py` |
| BENCH-NF-002 | ASC and BLF traces must be readable by the python-can readers and preserve identifier, format, FD, BRS and payload; ASC keeps exact microseconds and BLF stays within 1 µs. | `tests/test_bench_vector_trace.py` |
| BENCH-NF-003 | CI must need no Vector license or hardware; a hardware interface is used only when explicitly configured. | `tests/test_bench_bus.py` |
| BENCH-NF-004 | ASC and DBC exports must not depend on the host clock, locale or time zone. | `tests/test_bench_vector_trace.py` |

## XI-2 ECU communication

### Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-F-013 | Segment and reassemble ISO-TP (ISO 15765-2) messages up to 4,095 bytes with single, first, consecutive and flow-control frames, including the CAN FD escape single frame. | `tests/test_bench_isotp.py` |
| BENCH-F-014 | Honour the receiver's block size and STmin (1-127 ms and 100-900 µs), wrap sequence numbers after 15, and pad frames with a configurable byte. | `tests/test_bench_isotp.py` |
| BENCH-F-015 | Detect N_Bs and N_Cr timeouts, wrong sequence numbers, buffer overflow, too many WAIT frames, unexpected PDUs and malformed frames. | `tests/test_bench_isotp.py` |
| BENCH-F-016 | A UDS tester starts P2 when the request has been sent, switches to P2* after each 0x78 response-pending, and classifies the result as positive, negative, no response expected, P2 or P2* timeout, transport error or unexpected response. | `tests/test_bench_uds.py` |
| BENCH-F-017 | Apply the suppress-positive-response bit only to services that have a sub-function. | `tests/test_bench_uds.py` |
| BENCH-F-018 | A virtual ECU answers 0x10, 0x11, 0x14, 0x19, 0x22, 0x27, 0x2E and 0x3E with standard negative response codes, an S3 session timeout, a seed/key lockout with time delay, and response pending for slow DIDs. | `tests/test_bench_uds.py` |
| BENCH-F-019 | Supervise cyclic messages: report a message that never arrives, a timeout after its last frame, and recovery after a configurable number of frames. | `tests/test_bench_e2e_supervision.py` |
| BENCH-F-020 | Protect payloads with a 4-bit alive counter (0-14) and a CRC-8 SAE J1850 over a 16-bit data ID and the payload, and classify received frames as initial, OK, OK with some lost, repeated, wrong sequence, wrong CRC or invalid counter. | `tests/test_bench_e2e_supervision.py` |
| BENCH-F-021 | Inject drop, corrupted-CRC, repeated-counter and skipped-counter faults into a cyclic sender. | `tests/test_bench_e2e_supervision.py` |
| BENCH-F-022 | Run bench nodes on a deterministic simulated bus with frame times from the bitrates, or on a python-can bus with the wall clock, without changing node code. | `tests/test_bench_link.py` |
| BENCH-F-023 | Provide an ECU communication demo with an expected result for every diagnostic, E2E and supervision step, Vector traces and a JSON report, failing on any deviation. | `tools/run_ecu_communication_demo.py`, `tests/test_bench_ecu_demo.py` |

### Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-NF-005 | Transport, tester, ECU, supervision and E2E logic must not read a clock or touch a bus, so every timing rule is testable on logical time. | `tests/test_bench_isotp.py`, `tests/test_bench_uds.py` |
| BENCH-NF-006 | The CRC must match the CRC-8 SAE J1850 check value 0x4B and an independent implementation. | `tests/test_bench_e2e_supervision.py` |
| BENCH-NF-007 | The simulated demo must write identical traces on every run. | `tests/test_bench_ecu_demo.py` |
| BENCH-NF-008 | A simulated link must fail fast instead of looping when a node reports a deadline it never clears. | `tests/test_bench_link.py` |

## XI-3 Virtual airbag control unit

Thresholds are illustrative bench values, not a real ACU calibration. Test case IDs refer to
`tools/run_airbag_bench_demo.py`.

### Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-F-024 | At ignition on, the ACU runs a 6 s self-test with the warning lamp on, then switches the lamp off when no fault is active, and sends an E2E-protected status message every 100 ms. | ACU-T01 |
| BENCH-F-025 | Each of the four squib loops is valid between 1.5 and 5.0 Ω; below, above and open (≥ 20 Ω) raise loop DTCs B1001-B1004 with failure types 0x1A, 0x1B and 0x13. | ACU-T02, ACU-T03 |
| BENCH-F-026 | A failing condition sets testFailed and pending at once and confirmed after 500 ms; a repaired condition clears testFailed and keeps confirmed until a DTC clear; the lamp follows active confirmed faults. | ACU-T02, ACU-T03, ACU-T14 |
| BENCH-F-027 | Supply voltage below 9 V or above 16 V raises B1010 with failure type 0x16 or 0x17, confirmed after 2 s so an engine start does not confirm it. | ACU-T04, HIL-T06 |
| BENCH-F-028 | The vehicle status message is supervised; 500 ms without it raises U0121. | ACU-T05 |
| BENCH-F-029 | Deployment needs a delta-v over a 30 ms window confirmed by a safing sensor of at least 3 g: pretensioners at 6 km/h (driver if buckled, passenger if occupied), airbags at 14 km/h (passenger only if occupied and enabled), and nothing during the 200 ms arming delay. | ACU-T07, ACU-T08, ACU-T09, ACU-T13 |
| BENCH-F-030 | A hammer blow whose main-sensor delta-v exceeds the airbag threshold but is not confirmed by the safing sensor causes no deployment. | ACU-T06 |
| BENCH-F-031 | After supply loss the energy reserve keeps the firing path alive for 150 ms without CAN traffic; after that the ACU is off. | ACU-T10, ACU-T11 |
| BENCH-F-032 | The first firing stores a crash record and DTC B1050, sends an E2E-protected crash message at once and five more every 20 ms, and blocks any firing after the 100 ms crash event. The crash DTC survives a DTC clear. | ACU-T08, ACU-T14, ACU-T15 |
| BENCH-F-033 | A loop outside its valid window is reported as failed, not fired, in the crash record and crash message. | ACU-T12 |
| BENCH-F-034 | Diagnostic DIDs report loop resistances (0x4001-0x4004), supply voltage (0x4010), the crash record (0x4020) and system state with lamp (0x4030). | ACU-T04, ACU-T08 |
| BENCH-F-035 | Provide a system-test campaign whose cases list their requirements and compare every observation with an expected value, writing a JSON and Markdown report, the ACU DBC and traces of the severe crash. | `tools/run_airbag_bench_demo.py`, `tests/test_bench_airbag_demo.py` |

### Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-NF-009 | The campaign must fail on a miscalibrated ACU and on an ACU without safing confirmation, proving that its checks detect defects. | `tests/test_bench_airbag_demo.py` |
| BENCH-NF-010 | ACU CAN frames must be encoded from the same DBC that is exported, and decode with cantools. | `tests/test_bench_airbag.py` |
| BENCH-NF-011 | A test case must report a failed check instead of raising when the ACU misbehaves. | `tests/test_bench_airbag_demo.py` |

## XI-4 Bench instruments

Test case IDs refer to `tools/run_hil_bench_demo.py`. Voltage profiles follow the shape of
ISO 16750-2 tests with shortened durations; they are not certified test levels.

### Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-F-036 | Instruments accept SCPI commands with long or short mnemonics and optional nodes, IEEE 488.2 common commands (`*IDN?`, `*RST`, `*CLS`, `*OPC?`), channel lists such as `(@1,3)` and `(@1:4)`, and report errors through a `SYST:ERR?` queue with SCPI codes (-113, -200, -222, -224). | HIL-T01, HIL-T15 |
| BENCH-F-037 | A programmable supply sets and reads back KL30 voltage, switches its output, measures supply current and captures peak current. | HIL-T03, HIL-T14 |
| BENCH-F-038 | The supply runs named voltage profiles on logical time: momentary drop (4.5 V, 100 ms), dropout (0 V, 300 ms), starting profile, slow decrease and increase, and overvoltage (18 V). | HIL-T04 to HIL-T08 |
| BENCH-F-039 | A relay card switches KL15 on channel 1 and reports channel states. | HIL-T01 |
| BENCH-F-040 | A fault-injection box sets each squib loop to nominal, open, short to ground, short to battery or a substitute resistance, and the ACU reports failure types 0x11, 0x12, 0x13, 0x1A and 0x1B, including at the window boundaries. | HIL-T09, HIL-T10, HIL-T11 |
| BENCH-F-041 | A multimeter measures terminal voltage, supply current and loop resistance, reporting an open loop as overload (9.9E37). | HIL-T07, HIL-T11 |
| BENCH-F-042 | A climate chamber ramps temperature at a set rate; loop resistance drifts by 0.39 %/K from its 25 °C value, and the ACU raises B1060-4B above 85 °C. | HIL-T12, HIL-T13 |
| BENCH-F-043 | The ACU draws at most 100 µA with KL15 off, constant 1.8 W when running and 1.75 A per firing squib for 2 ms; it survives supply drops up to its 150 ms energy reserve and repeats its self-test after longer ones. | HIL-T02 to HIL-T06, HIL-T14 |
| BENCH-F-044 | Provide a HiL campaign that drives the ACU only through instruments and UDS, logs every SCPI command with its time and answer, and writes JSON and Markdown reports. | `tools/run_hil_bench_demo.py`, `tests/test_bench_hil_demo.py` |

### Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| BENCH-NF-012 | `SimulatedLink.run_until` limits time relative to the call, and a diagnostic request that gets no result raises instead of returning an older response. | `tests/test_bench_link.py` |
| BENCH-NF-013 | Instrument errors never raise into the test script; they go to the error queue, as on real instruments. | `tests/test_bench_scpi.py`, HIL-T15 |
| BENCH-NF-014 | The HiL campaign must fail on an ACU with excessive quiescent current, a supply debounce shorter than an engine start, a missing energy reserve or a wrong resistance window. | `tests/test_bench_hil_demo.py` |

## Deliberate limits

- The bench simulates the network and the logic of a test bench. It does not model analog
  signals, electrical timing, bit stuffing on the wire or real EMC behaviour.
- python-can can drive real interfaces (Vector, PEAK, SocketCAN, slcan). ATEP CI only uses the
  `virtual` interface.
- ISO-TP messages are limited to 4,095 bytes; the 32-bit first-frame length escape is not
  implemented. Functional (broadcast) addressing is not modelled.
- Instruments are models: no measurement noise, accuracy class, settling time or current limit.
- The ACU deployment algorithm, thresholds and timings are illustrative. Real calibrations are
  confidential, use more sensors (side, satellite, rollover) and are validated with physical
  crash tests.
- The virtual ECU's seed/key algorithm is a public XOR mask for teaching. The E2E model follows
  AUTOSAR E2E Profile 1 ideas but is not a certified implementation.
