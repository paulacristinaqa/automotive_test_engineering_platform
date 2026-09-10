# ATEP Volume IX AI Test Engineer Engineering Workbook

Version 0.3.0 records the IX-1 provider-neutral foundation, IX-2 deterministic workers, and IX-3
log intelligence. It keeps governed analysis and evidence processing local and reproducible.

## Scope and architecture

FastAPI validates bounded requests. The domain service enforces idempotency and data policy.
PostgreSQL stores immutable queued intent. RBAC protects creation and retrieval. Audit and outbox
records provide minimized traceability. A versioned local rule adapter now produces structured,
evidence-linked advisory results without invoking an AI provider.
IX-3 adds bounded parsing, sanitization, chronological timelines, stable message clustering,
deterministic anomaly signals, and explanations tied to source line numbers.

## Engineering decisions

- Default to `local_only`; external providers require explicit request policy.
- Reject restricted data before any future external adapter can receive it.
- Store references and bounded context instead of copying artifact bodies.
- Keep AI advisory and outside vehicle and test state mutation paths.
- Use a deterministic local rule worker before optional LLM adapters.
- Persist immutable attempts and limit failed retries to three.
- Disable unknown adapters and enforce policy before future external processing.

## Tests and objectives

- Contract bounds prevent uncontrolled context and evidence growth.
- Policy tests prevent restricted-data egress.
- Replay tests prove retry safety and stable conflict behavior.
- Event tests prove raw prompts and context are absent from integration evidence.
- RBAC and OpenAPI tests prove the public boundary.
- Hosted Docker integration proves migration 0057 on PostgreSQL.
- Worker tests verify deterministic findings, lifecycle, retry limits, safe failures, and replay.
- Hosted Docker integration proves migration 0059 and execution persistence on PostgreSQL.
- Log tests verify parsing, redaction, clustering, anomalies, grounded explanations, and bounds.
- Hosted Docker integration proves migration 0060 and log evidence persistence on PostgreSQL.

## IX-2 outcome

The local worker recognizes supplied DTCs, positive failure counts, and failed performance
thresholds. It produces summaries, findings, recommendations, confidence, and citations limited to
the request evidence. It requires no model, API key, paid account, network, or GPU.

## Next increment

IX-4 adds requirement-aware test suggestions with human review, rejection evidence, and controlled
promotion into the test catalog. No generated suggestion may activate or execute itself.
