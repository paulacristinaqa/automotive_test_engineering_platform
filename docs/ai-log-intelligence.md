# AI Log Intelligence

Volume IX-3 turns bounded text logs into deterministic, reviewable evidence. It is attached to a
governed log-analysis, failure-explanation, or root-cause request and runs without an AI model,
network access, paid service, or GPU.

## Input contract

Each analysis accepts one to 500 lines and no more than 256,000 encoded bytes. The supported format
begins with an ISO 8601 timestamp carrying `Z` or an explicit offset, followed by a severity, optional
component in brackets, and message. Unsupported lines are counted but their text is not persisted.
The parsed timeline may span at most seven days.

## Sanitization and parsing

Before persistence, the parser replaces email addresses, bearer credentials, password, token,
secret and API-key values, and VIN-like identifiers. It normalizes `WARN` to `warning`, preserves the
original line number, and orders events by their actual timezone-aware timestamp.

## Clustering and anomalies

Clustering lowercases messages and replaces volatile UUID, hexadecimal, and numeric values before
calculating a stable 16-character fingerprint. A cluster becomes a severe-event anomaly when it
contains an error or critical record. Three matching events within ten seconds produce one burst
anomaly. These are deterministic signals, not causal conclusions.

## Grounded explanation

The explanation reports parsed, rejected, cluster, and anomaly counts. It cites the source line
numbers supporting detected signals and only evidence references already governed by the request.
Explicit limitations state that vehicle state and cited artifacts require human review before any
causal conclusion.

## API and evidence

- `POST /api/v1/ai/analysis-requests/{request_id}/log-intelligence`
- `GET /api/v1/ai/log-analyses`
- `GET /api/v1/ai/log-analyses/{analysis_id}`

Creation uses `ai_analysis:manage`; reads use `ai_analysis:read`. Resource, audit, and
`atep.ai.log_analysis.completed.v1` outbox evidence share one transaction. Integration evidence
contains identifiers and counts, never raw lines, messages, timelines, or explanation text.
