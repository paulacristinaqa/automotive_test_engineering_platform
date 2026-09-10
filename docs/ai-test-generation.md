# AI Test Generation

Volume IX-4 creates deterministic, requirement-aware test suggestions while preserving human
authority over the test catalog. It requires no model, API key, network access, paid service, or GPU.

## Workflow

1. Create a governed analysis request with task `test_suggestion`.
2. Submit bounded requirement and evidence references plus the test objective.
3. ATEP creates a catalog-compatible suggestion in `draft`.
4. An authorized reviewer approves or rejects it with a version and comment.
5. A separate authorized promotion may convert an approved suggestion into a catalog definition.
6. The promoted definition remains `draft` and cannot execute until the existing catalog governance
   activates it explicitly.

The states are `draft`, `approved`, `rejected`, and `promoted`. Rejected suggestions are terminal so
their reasoning remains stable evidence. Exact retries are safe; changed reuse returns HTTP 409.

## Public API

- `POST /api/v1/ai/analysis-requests/{request_id}/test-suggestions`
- `GET /api/v1/ai/test-suggestions`
- `GET /api/v1/ai/test-suggestions/{suggestion_id}`
- `POST /api/v1/ai/test-suggestions/{suggestion_id}/review`
- `POST /api/v1/ai/test-suggestions/{suggestion_id}/promotion`

Read operations require `ai_analysis:read`; mutations require `ai_analysis:manage`. Creation,
review, and promotion append minimized audit and outbox evidence atomically. Candidate steps,
objectives, and reviewer comments are excluded from event payloads.

## Safety boundary

Generation is advisory. It cannot activate a catalog definition, create a run, schedule a job,
change vehicle state, or execute a command. Requirement references support traceability but do not
prove compliance; the reviewer remains responsible for correctness, coverage, and safety relevance.
