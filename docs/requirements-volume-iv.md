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
