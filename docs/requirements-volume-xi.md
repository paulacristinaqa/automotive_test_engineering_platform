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

## Deliberate limits

- The bench simulates the network and the logic of a test bench. It does not model analog
  signals, electrical timing, bit stuffing on the wire or real EMC behaviour.
- python-can can drive real interfaces (Vector, PEAK, SocketCAN, slcan). ATEP CI only uses the
  `virtual` interface.
