# ATEP Volume IX AI Test Engineer Engineering Workbook

Version 0.4.0 records IX-1 through IX-4, including governed test suggestions, human review, and
controlled promotion. Analysis and evidence processing remain local and reproducible.

## Scope and architecture

FastAPI validates bounded requests. The domain service enforces idempotency and data policy.
PostgreSQL stores immutable queued intent. RBAC protects creation and retrieval. Audit and outbox
records provide minimized traceability. A versioned local rule adapter now produces structured,
evidence-linked advisory results without invoking an AI provider.
IX-3 adds bounded parsing, sanitization, chronological timelines, stable message clustering,
deterministic anomaly signals, and explanations tied to source line numbers.
IX-4 converts governed requirement and evidence references into catalog-compatible drafts. Review
and promotion are separate versioned operations, and promotion creates an inactive catalog draft.

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
- Suggestion tests verify bounds, deterministic drafts, review states, rejection evidence, and replay.
- Promotion tests prove that only approved suggestions become inactive catalog definitions.
- Hosted Docker integration proves migration 0061 and end-to-end traceability on PostgreSQL.

## IX-2 outcome

The local worker recognizes supplied DTCs, positive failure counts, and failed performance
thresholds. It produces summaries, findings, recommendations, confidence, and citations limited to
the request evidence. It requires no model, API key, paid account, network, or GPU.

## IX-4 outcome

Suggestions preserve requirement and evidence references, a bounded candidate, and rationale. An
authorized reviewer must approve or reject with a comment. A separate promotion creates a test
definition in `draft`; generated content never activates, schedules, or executes itself.

## Next increment

IX-5 adds evidence-ranked root-cause hypotheses, explainable risk scoring, and prediction evaluation.
