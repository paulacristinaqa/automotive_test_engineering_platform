# ATEP Volume IV - CAN Network Requirements

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| CAN-F-001 | The platform shall create at most one CAN network per vehicle. | Implemented |
| CAN-F-002 | A network shall reference 1-64 ECUs belonging to the same vehicle. | Implemented |
| CAN-F-003 | A network shall contain at most 256 uniquely identified frame contracts. | Implemented |
| CAN-F-004 | Standard IDs shall be limited to 11 bits and extended IDs to 29 bits. | Implemented |
| CAN-F-005 | Classic CAN DLC shall be limited to 0-8 bytes. | Implemented |
| CAN-F-006 | Only the declared producer shall submit a contracted frame. | Implemented |
| CAN-F-007 | Submission shall assign deterministic sequence and logical time evidence. | Implemented |
| CAN-F-008 | Exact command replay shall not increment time, sequence, or version twice. | Implemented |
| CAN-F-009 | Changed command-ID reuse shall return a stable conflict. | Implemented |
| CAN-F-010 | Network reads and management shall use independent RBAC permissions. | Implemented |
| CAN-F-011 | Network creation and frame submission shall produce atomic audit/outbox evidence. | Implemented |
| CAN-F-012 | Frame history pagination shall enforce safe limits. | Implemented |
| CAN-F-013 | The platform shall arbitrate batches of 1-64 unique contracted contenders. | Implemented |
| CAN-F-014 | The lowest ready numeric CAN ID shall win; standard format shall precede extended format for equal IDs. | Implemented |
| CAN-F-015 | Arbitration shall calculate nominal classic CAN bit count and microsecond duration from configured bitrate. | Implemented |
| CAN-F-016 | Arbitration shall persist ordered transmission and declared-consumer delivery evidence. | Implemented |
| CAN-F-017 | Arbitration shall report occupied, idle, utilization, and maximum-latency metrics. | Implemented |
| CAN-F-018 | One successful batch shall increment aggregate version once and sequence once per frame. | Implemented |
| CAN-F-019 | Exact arbitration replay shall be mutation-free; changed command reuse shall return a stable conflict. | Implemented |
| CAN-F-020 | Arbitration history and detail shall be protected and safely queryable. | Implemented |
| CAN-F-021 | The platform shall create at most one structured DBC catalogue per CAN network. | Implemented |
| CAN-F-022 | Each DBC message shall reference an existing frame contract and contain unique, non-overlapping signals within its DLC. | Implemented |
| CAN-F-023 | Signals shall define start bit, bit length, Intel or Motorola byte order, signedness, factor, offset, optional physical bounds, and unit. | Implemented |
| CAN-F-024 | Intel signals shall use contiguous LSB-first DBC bit numbering. | Implemented |
| CAN-F-025 | Motorola signals shall use MSB-first DBC sawtooth bit numbering. | Implemented |
| CAN-F-026 | Encoding shall require exactly the declared signals and reject values that are not exactly representable. | Implemented |
| CAN-F-027 | Encoding and decoding shall support unsigned and two's-complement signed raw values. | Implemented |
| CAN-F-028 | Codec execution shall persist payload, raw values, and physical values as replayable evidence. | Implemented |
| CAN-F-029 | Exact codec replay shall be mutation-free; changed command reuse shall return a stable conflict. | Implemented |
| CAN-F-030 | DBC catalogue and codec evidence shall be protected by CAN read/manage permissions. | Implemented |
| CAN-F-031 | A CAN FD-enabled network shall define nominal and data-phase bitrates. | Implemented |
| CAN-F-032 | CAN FD frame contracts shall accept only ISO-defined payload lengths through 64 bytes. | Implemented |
| CAN-F-033 | Classic frame contracts shall remain limited to eight bytes on FD-enabled mixed networks. | Implemented |
| CAN-F-034 | Bitrate switching shall be rejected for classic CAN frame contracts. | Implemented |
| CAN-F-035 | Frame submission and arbitration shall preserve protocol and bitrate-switch metadata. | Implemented |
| CAN-F-036 | CAN FD timing shall expose nominal and data bit counts and phase durations. | Implemented |
| CAN-F-037 | Arbitration shall run at the nominal bitrate and apply the data bitrate only to BRS-enabled FD data phases. | Implemented |
| CAN-F-038 | Classic and FD contenders shall share the same deterministic CAN identifier priority rules. | Implemented |
| CAN-F-039 | DBC signals and codec payloads shall support contracted CAN FD payloads through 512 bits. | Implemented |
| CAN-F-040 | CAN FD aggregate events shall report frame counts and timing metadata without payload bytes. | Implemented |
| CAN-F-041 | Transmission faults shall increment TEC by eight per occurrence and reception faults shall increment REC by one. | Implemented |
| CAN-F-042 | Nodes shall transition to error-passive at TEC or REC 128 and bus-off at TEC 256. | Implemented |
| CAN-F-043 | A bus-off producer shall be excluded from direct submission and arbitration. | Implemented |
| CAN-F-044 | Frame-loss injection shall preserve TEC and REC while recording deterministic loss evidence. | Implemented |
| CAN-F-045 | Fault targets shall conform to the producer or consumer role declared by the frame contract. | Implemented |
| CAN-F-046 | Bus-off recovery shall require at least 128 sequences of 11 recessive bits and reset TEC/REC. | Implemented |
| CAN-F-047 | Fault and recovery commands shall support exact idempotent replay and stable changed-reuse conflicts. | Implemented |
| CAN-F-048 | Fault executions shall be queryable by bounded history and command identifier. | Implemented |
| CAN-F-049 | Fault and recovery operations shall produce atomic audit and outbox evidence. | Implemented |
| CAN-F-050 | Network reads shall expose the current error state of affected nodes. | Implemented |
| CAN-F-051 | The network aggregate shall configure at most eight bounded LIN channels. | Implemented |
| CAN-F-052 | LIN frame identifiers shall be six-bit values with one publisher, 1-15 subscribers, and 1-8 payload bytes. | Implemented |
| CAN-F-053 | LIN channels shall use a bitrate from 1 through 20 kbit/s and explicit checksum semantics. | Implemented |
| CAN-F-054 | The aggregate shall configure at most eight automotive Ethernet segments at 100 or 1000 Mbit/s. | Implemented |
| CAN-F-055 | Ethernet messages shall define EtherType, source, destinations, optional VLAN, and 1-1500 payload bytes. | Implemented |
| CAN-F-056 | Gateway routes shall connect different protocols and reference an ECU declared with gateway role. | Implemented |
| CAN-F-057 | Transparent gateway routes shall require equal source and destination payload lengths. | Implemented |
| CAN-F-058 | Route execution shall assign deterministic sequence, logical start/completion time, and destination timing. | Implemented |
| CAN-F-059 | Configuration and routing shall support exact replay and stable changed-command conflicts. | Implemented |
| CAN-F-060 | Multi-bus configuration and route evidence shall be protected, safely paginated, audited, and evented. | Implemented |

## Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| CAN-NF-001 | Simulation results shall not depend on host wall-clock, CPU, or GPU timing. | Implemented |
| CAN-NF-002 | Aggregate configuration and API responses shall be explicitly bounded. | Implemented |
| CAN-NF-003 | Payload bytes shall be excluded from audit and outbox evidence. | Implemented |
| CAN-NF-004 | Database changes shall be versioned and reversible through Alembic. | Implemented |
| CAN-NF-005 | OpenAPI shall publish typed contracts and safe pagination constraints. | Implemented |
| CAN-NF-006 | Ruff, strict mypy, pytest, and integration CI shall protect the baseline. | Implemented |
| CAN-NF-007 | Arbitration order and timing shall remain reproducible across host resource conditions. | Implemented |
| CAN-NF-008 | Arbitration events and audit shall expose aggregate metrics without CAN payload bytes. | Implemented |
| CAN-NF-009 | Decimal scaling and offset calculations shall avoid binary floating-point drift. | Implemented |
| CAN-NF-010 | Codec audit and outbox evidence shall exclude payload and signal values. | Implemented |
| CAN-NF-011 | Codec commands shall serialize on the network aggregate to prevent duplicate concurrent evidence. | Implemented |
| CAN-NF-012 | Existing classic CAN contracts and timing results shall remain backward compatible. | Implemented |
| CAN-NF-013 | CAN FD timing shall be deterministic and independent of host performance. | Implemented |
| CAN-NF-014 | CAN FD persistence changes shall be reversible through Alembic. | Implemented |
| CAN-NF-015 | Fault timing and counter transitions shall be independent of host CPU, GPU, and wall clock. | Implemented |
| CAN-NF-016 | Fault audit and outbox records shall exclude CAN payload bytes and full request bodies. | Implemented |
| CAN-NF-017 | Error-state and execution persistence shall be reversible through Alembic. | Implemented |
| CAN-NF-018 | LIN and Ethernet timing shall remain deterministic across host CPU, GPU, and wall-clock conditions. | Implemented |
| CAN-NF-019 | Gateway audit and outbox evidence shall exclude routed payload bytes and full configuration bodies. | Implemented |
| CAN-NF-020 | Multi-bus persistence changes shall be reversible through Alembic. | Implemented |
