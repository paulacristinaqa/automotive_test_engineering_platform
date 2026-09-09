# AI Analysis Workers

Volume IX-2 executes governed analysis requests through a provider-neutral adapter boundary. The
default and only enabled adapter is `local-rules`, a deterministic CPU-only implementation that does
not call the network or load an AI model.

## Lifecycle and retries

A request begins as `queued`, changes to `running` during adapter execution, and finishes as
`succeeded` or `failed`. Each attempt creates an immutable execution record. Only failed requests may
be retried, with a maximum of three attempts. Exact retries of the same execution identifier return
the original record; changed reuse returns a stable conflict.

## Local rules

Version `local-rules-v1` recognizes diagnostic trouble codes, positive failure counts, and failed
performance thresholds supplied in structured context. It emits bounded findings and practical
review recommendations. When no rule matches, it explicitly reports insufficient deterministic
signal instead of inventing a cause.

## Provider and privacy boundary

All adapters implement the same analysis interface. Unknown adapters are disabled. A future external
adapter must pass both provider-policy and data-classification checks before it can receive data.
Restricted data can never use an external adapter. Worker failures retain a stable error code and do
not copy exception details into API output, audit, or events.

## API

- `POST /api/v1/ai/analysis-requests/{request_id}/executions`
- `GET /api/v1/ai/analysis-requests/{request_id}/executions`

Both operations use the existing `ai_analysis:manage` and `ai_analysis:read` permissions. Completion
publishes `atep.ai.analysis.completed.v1` with identities, counts, lifecycle, and adapter version but
without context, instructions, result text, or evidence contents.
