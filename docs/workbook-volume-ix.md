# ATEP Volume IX AI Test Engineer Engineering Workbook

Version 0.1.0 records the IX-1 provider-neutral foundation. It separates governed analysis intent
from future model execution and establishes a no-cost, local-first baseline.

## Scope and architecture

FastAPI validates bounded requests. The domain service enforces idempotency and data policy.
PostgreSQL stores immutable queued intent. RBAC protects creation and retrieval. Audit and outbox
records provide minimized traceability. No AI provider is invoked in this increment.

## Engineering decisions

- Default to `local_only`; external providers require explicit request policy.
- Reject restricted data before any future external adapter can receive it.
- Store references and bounded context instead of copying artifact bodies.
- Keep AI advisory and outside vehicle and test state mutation paths.
- Add a deterministic local rule worker before optional LLM adapters.

## Tests and objectives

- Contract bounds prevent uncontrolled context and evidence growth.
- Policy tests prevent restricted-data egress.
- Replay tests prove retry safety and stable conflict behavior.
- Event tests prove raw prompts and context are absent from integration evidence.
- RBAC and OpenAPI tests prove the public boundary.
- Hosted Docker integration proves migration 0057 on PostgreSQL.

## Next increment

IX-2 adds lifecycle and result contracts plus a deterministic local rule engine. Optional provider
adapters remain disabled by default and must implement the same policy boundary.
