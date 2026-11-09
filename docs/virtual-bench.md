# Virtual Test Bench

Volume XI turns ATEP evidence into the artifacts a system-test engineer uses at a Vector CANoe
bench, and adds a python-can bus so the same test code can run against a virtual bus or a real
CAN interface. Requirements are in [requirements-volume-xi.md](requirements-volume-xi.md) and the
plan in [roadmap-volume-xi.md](roadmap-volume-xi.md).

## XI-1 Real CAN stack and Vector artifacts

```mermaid
flowchart LR
    Evidence["ATEP CAN network, DBC catalogue, frame evidence"] --> DBC["network.dbc"]
    Evidence --> ASC["trace.asc"]
    Evidence --> BLF["trace.blf"]
    DBC --> CANoe["CANoe / CANalyzer"]
    ASC --> CANoe
    BLF --> CANoe
    Schedule["Cyclic schedule encoded by the ATEP codec"] --> Bus["Bench bus (python-can)"]
    Bus --> Monitor["Monitor node"]
    Monitor --> Cantools["cantools decode (independent check)"]
```

### Exports API

Both endpoints need `can_networks:read`, change nothing and are rate limited like every API route.

- `GET /api/v1/vehicles/{vehicle_id}/can-networks/exports/dbc` returns the network as a DBC file
  (Windows-1252, CRLF). Without a DBC catalogue the file still lists every frame contract, with
  no signals.
- `GET /api/v1/vehicles/{vehicle_id}/can-networks/exports/trace?format=asc|blf&after_sequence=0&limit=10000`
  returns submitted frames in sequence order. Response headers: `X-ATEP-Frame-Count`,
  `X-ATEP-Last-Sequence` and `X-ATEP-Truncated`. To page, pass the last sequence as
  `after_sequence`.

### How ATEP maps to DBC

| ATEP | DBC |
|---|---|
| Frame contract `bms-status` | `BO_ 384 bms_status` (non-identifier characters become `_`) |
| Extended frame | Message ID with bit 31 set, `VFrameFormat` = `ExtendedCAN` |
| CAN FD frame | `VFrameFormat` = `StandardCAN_FD` or `ExtendedCAN_FD`; `CANFD_BRS` = 1 with bitrate switch |
| Producer and consumers | Sender node and signal receivers (`Vector__XXX` when none) |
| Intel / Motorola | `@1` / `@0`, start bit as stored by ATEP (MSB for Motorola) |
| No declared min/max | Range derived from the raw range, factor and offset |
| ECU without a record | Node name `ECU_<uuid hex>` |

Names that collide after conversion are rejected with `can_network_contract_invalid`.

### Timing in traces

- ATEP time is logical microseconds. ASC keeps it exactly; BLF stays within 1 µs.
- Measurement start is the network creation time in UTC, truncated to milliseconds.
- ASC and DBC output do not depend on the host clock, locale or time zone. BLF output is
  reproducible for identical input.

### Bench bus

`atep.bench.bus.BenchBusConfig` selects a python-can interface: `virtual` (default, no
hardware), `socketcan`, `vector`, `pcan` or `slcan`. Any other interface is rejected.
`replay_frames` sends frames at once (deterministic mode) or paced by their timestamps
(real-time mode).

### Demo

```bash
python tools/run_virtual_bench_demo.py --output out/virtual-bench
```

The demo sends one second of traffic for the reference CAN FD powertrain network (BMS and VCU,
three cyclic messages at 10, 20 and 100 ms), receives it on a second node and decodes every frame
with cantools. It writes `network.dbc`, `trace.asc`, `trace.blf` and `report.json`, and exits
with code 1 on any mismatch. Add `--realtime` to pace frames on the wall clock. With a real
interface, for example `--interface vector --channel 0`, the same traffic goes to hardware.

To inspect the result in CANoe or CANalyzer, add `network.dbc` as the database and open
`trace.asc` or `trace.blf` in offline mode.

## XI-2 ECU communication

XI-2 adds the protocols a system tester exercises on a bench: ISO-TP transport, UDS diagnostics
with response timing, cyclic message supervision and E2E protection. Every protocol is a
*sans-IO* node: it receives frames and the current logical time, and returns frames to send. It
never reads a clock or touches a bus, so the same node runs on two kinds of link.

```mermaid
flowchart LR
    subgraph Nodes["Bench nodes (no I/O)"]
        Tester["UdsClient + ISO-TP"]
        Ecu["VirtualEcu + ISO-TP"]
        Sender["CyclicSender + E2E"]
        Receiver["E2EReceiver"]
        Monitor["TimeoutMonitor"]
    end
    Nodes --> Sim["SimulatedLink: logical time, frame times from bitrate"]
    Nodes --> Real["BusNodeRunner: python-can bus, wall clock"]
    Sim --> Trace["ASC / BLF trace"]
```

### ISO-TP (`atep.bench.isotp`)

| Frame | First byte | Use |
|---|---|---|
| Single frame | `0L` (or `00 LL` on CAN FD) | Payload up to 7 bytes (62 on CAN FD with 64-byte frames) |
| First frame | `1L LL` | Starts a longer message, up to 4,095 bytes |
| Consecutive frame | `2N` | Next chunk; N counts 1..15 then wraps to 0 |
| Flow control | `3S BS ST` | Receiver says continue (0), wait (1) or overflow (2), with block size and STmin |

The sender waits up to N_Bs for each flow control and the receiver waits up to N_Cr for each
consecutive frame. Errors are reported as events, not exceptions.

### UDS tester and virtual ECU (`atep.bench.uds`, `atep.bench.virtual_ecu`)

- P2 (50 ms) runs from the end of the request transmission to the start of the response.
  A `7F <SID> 78` response-pending answer switches the wait to P2* (5 s).
- Bit 7 of the sub-function suppresses the positive response, only for services that have a
  sub-function. `22 F1 90` is not suppressed even though `0xF1` has bit 7 set.
- The virtual ECU supports session control, ECU reset, clear and read DTC (by status mask),
  read and write DID, security access and tester present. Non-default sessions fall back after
  S3 (5 s) without traffic. Three wrong keys lock security access for a delay. DIDs listed in
  `slow_dids` answer with response pending.

### Supervision and E2E (`atep.bench.supervision`, `atep.bench.e2e`, `atep.bench.cyclic`)

- `TimeoutMonitor` reports `waiting`, `ok` and `timeout` per message, including a message that
  never arrives, and debounces recovery.
- E2E stamps a 4-bit alive counter (0-14) and a CRC-8 SAE J1850 over a 16-bit data ID and the
  payload. The checker returns `initial`, `ok`, `ok_some_lost`, `repeated`, `wrong_sequence`,
  `wrong_crc` or `invalid_counter`.
- `CyclicSender` injects drop, corrupted-CRC, repeated-counter and skipped-counter faults on
  chosen cycles.

### Demo

```bash
python tools/run_ecu_communication_demo.py --output out/ecu-communication
```

The demo runs a 19-step diagnostic session (multi-frame transfers with flow control, security
access with a wrong key, response pending, suppressed response, DTCs, S3 timeout, reset) and an
E2E scenario with injected faults and timeout supervision. Each step has an expected result. It
writes `diagnostics.asc/.blf`, `e2e.asc/.blf` and `report.json`. Add `--bus virtual` to run the
diagnostic session on a python-can bus with the wall clock instead of the simulated link.

## Limits

- The bench simulates the network and test logic. There is no electrical layer, no bit stuffing
  on the wire and no error frames from a physical bus.
- The trace export covers submitted frames. Arbitration batches and multi-bus campaigns are not
  exported yet.
- cantools is a development dependency. It checks ATEP output and is not used by the API.
