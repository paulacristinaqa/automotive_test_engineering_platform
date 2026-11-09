# ATEP Volume XI Virtual Test Bench Engineering Workbook

Version 0.1.0 delivers XI-1: Vector-compatible DBC, ASC and BLF artifacts from ATEP evidence,
and a python-can bench bus that runs the same traffic on a virtual bus or a real CAN interface.

## Scope and architecture

The `atep.bench` package sits beside the CAN network domain and only reads its data. Pure
renderers turn a network specification into DBC text and a list of trace frames into ASC text or
BLF bytes. A thin export service loads the network, its optional DBC catalogue, ECU names and
submitted frames. Two read-only endpoints serve the files under
`/vehicles/{vehicle_id}/can-networks/exports`.

The bench bus wraps python-can behind an interface allowlist. The demo tool encodes cyclic traffic
with the ATEP codec, sends it on the bus, receives it on a second node and decodes it with
cantools, an implementation independent of ATEP. Architecture details are in
[virtual-bench.md](virtual-bench.md).

## Engineering decisions

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
| The demo passes end to end and writes identical files on every run | `tests/test_bench_demo.py` |

## Risks and technical debt

- The bench has no electrical layer. Bench instruments and transients arrive in XI-4 and XI-5,
  as models, not measurements.
- Arbitration batches and multi-bus campaigns are not yet exported as traces.
- The DBC export does not write value tables (`VAL_`) or multiplexed signals, because ATEP does
  not model them yet.
- The Vector import of the generated files is checked with python-can and cantools, not with
  CANoe itself. Open the demo files in CANoe or CANalyzer to confirm.
- The formatted `.docx` workbook for this volume is not built yet.

## XI-1 outcome

XI-1 is complete. `tools/run_virtual_bench_demo.py` sends 160 frames per second of reference
traffic on the virtual bus with no payload, encoding or decoding mismatch.

## Next increment

XI-2 ECU communication: ISO-TP, UDS over CAN frames with P2/P2* timing, cyclic message timeout
supervision and E2E protection.
