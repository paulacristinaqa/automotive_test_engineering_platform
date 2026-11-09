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

## Deliberate limits

- The bench simulates the network and the logic of a test bench. It does not model analog
  signals, electrical timing, bit stuffing on the wire or real EMC behaviour.
- python-can can drive real interfaces (Vector, PEAK, SocketCAN, slcan). ATEP CI only uses the
  `virtual` interface.
- ISO-TP messages are limited to 4,095 bytes; the 32-bit first-frame length escape is not
  implemented. Functional (broadcast) addressing is not modelled.
- The virtual ECU's seed/key algorithm is a public XOR mask for teaching. The E2E model follows
  AUTOSAR E2E Profile 1 ideas but is not a certified implementation.
