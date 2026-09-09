# Fault Campaigns

Volume VIII-5 adds a safe orchestration and evidence layer for fault injection. It does not replace
the native fault mechanisms owned by the Digital Vehicle, ECU, CAN, diagnostics, Electric Vehicle,
or ADAS modules.

## Responsibility boundary

The Test Framework owns campaign definitions, lifecycle, ordered execution snapshots, safety
bounds, recovery intent, progress, aggregate outcome, audit, and transactional outbox evidence.
Domain simulators own the actual state mutation and restoration. Cross-platform automatic dispatch
through native adapters remains an isolated integration concern. No API in VIII-5 accepts an
arbitrary command or code.

## Safety model

- Campaign blast radius is limited to one component, one network, or one vehicle.
- A campaign contains at most 32 ordered steps.
- Every action belongs to a domain-specific allowlist.
- Every step has an expected effect and mandatory recovery action, timeout, and verification.
- Structured parameters are limited to 8,192 bytes.
- Total injection plus recovery time is limited to 30 minutes.
- Audit and event payloads retain counts and fingerprints, not raw parameters or evidence references.

## Lifecycle

Campaigns follow `draft -> active -> archived` with optimistic versions. Only active campaigns can
start new executions. An exact idempotent replay remains valid after archival because the existing
execution snapshot is authoritative.

Execution steps follow these forward-only paths:

```text
pending -> injecting -> injected -> recovering -> recovered
       \-> skipped         \-> failed       \-> failed
             injecting -----------------------> failed
```

An execution is running after progress begins. When all steps are terminal, a failed or skipped
required step produces a failed execution; otherwise it passes. An incomplete execution can be
cancelled by an authorized operator.

## API

- `POST /api/v1/fault-campaigns`
- `GET /api/v1/fault-campaigns`
- `GET /api/v1/fault-campaigns/{campaign_id}`
- `PATCH /api/v1/fault-campaigns/{campaign_id}/status`
- `POST /api/v1/fault-campaigns/{campaign_id}/executions`
- `GET /api/v1/fault-executions`
- `GET /api/v1/fault-executions/{execution_id}`
- `GET /api/v1/fault-executions/{execution_id}/steps`
- `PATCH /api/v1/fault-executions/{execution_id}/steps/{step_id}`
- `PATCH /api/v1/fault-executions/{execution_id}/cancel`

Reads require `test_catalog:read`; mutations require `test_catalog:manage`.

## Events

- `atep.fault_campaign.created.v1`
- `atep.fault_campaign.status_changed.v1`
- `atep.fault_campaign.execution.requested.v1`
- `atep.fault_campaign.step_recorded.v1`
- `atep.fault_campaign.execution.cancelled.v1`

All accepted mutations persist their resource change, audit record, and outbox event in the same
database transaction.
