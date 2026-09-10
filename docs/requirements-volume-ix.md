# Volume IX AI Test Engineer Requirements

## IX-1 functional requirements

- **AI-F-001** The platform shall accept analysis requests for logs, failure explanations, test
  suggestions, root cause, and risk analysis.
- **AI-F-002** Every request shall identify one supported ATEP subject and bounded evidence references.
- **AI-F-003** Provider policy shall explicitly distinguish local-only from external-allowed processing.
- **AI-F-004** Restricted data shall be rejected when external processing is allowed.
- **AI-F-005** Exact retries shall return the original request; changed reuse shall return stable HTTP 409.
- **AI-F-006** Creation, audit, and `atep.ai.analysis.requested.v1` outbox evidence shall be atomic.
- **AI-F-007** Audit and events shall exclude raw context, instructions, and evidence content.
- **AI-F-008** Read and management operations shall require `ai_analysis:read` and
  `ai_analysis:manage` respectively.
- **AI-F-009** Collection APIs shall provide bounded pagination and task filtering.

## Non-functional requirements

- **AI-NF-001** The baseline shall operate without a cloud account, paid API, model download, or GPU.
- **AI-NF-002** Context shall not exceed 16384 encoded bytes and evidence lists shall not exceed 50 items.
- **AI-NF-003** External model execution shall be absent from IX-1; future adapters must enforce policy
  before transmitting data.
- **AI-NF-004** AI output shall be advisory and shall never directly mutate vehicle or test state.

## IX-2 functional requirements

- **AI-F-010** Execute queued analysis requests through a versioned deterministic local rule adapter.
- **AI-F-011** Store one immutable execution record per bounded attempt and update request lifecycle.
- **AI-F-012** Limit requests to three attempts and allow retries only after a failed attempt.
- **AI-F-013** Return structured summaries, findings, recommendations, confidence, and evidence references.
- **AI-F-014** Make exact execution retries idempotent and changed identifier reuse a stable conflict.
- **AI-F-015** Keep provider adapters behind one common interface and disable unknown adapters.
- **AI-F-016** Enforce provider policy and data classification before any external adapter invocation.
- **AI-F-017** Persist minimized completion audit and outbox evidence atomically with each attempt.
- **AI-NF-005** The local adapter shall require no model, API key, network access, paid service, or GPU.
- **AI-NF-006** Adapter failures shall expose a stable code without leaking internal exception details.
- **AI-NF-007** Results shall remain advisory and cite only evidence supplied with the request.

## IX-3 functional requirements

- **AI-F-018** Accept one to 500 bounded timestamped log lines for a governed analysis request.
- **AI-F-019** Parse supported ISO 8601 records into a deterministic chronological timeline.
- **AI-F-020** Sanitize credentials, email addresses, and VIN-like identifiers before persistence.
- **AI-F-021** Cluster messages after normalizing volatile UUID, hexadecimal, and numeric values.
- **AI-F-022** Identify severe-level clusters and repeated bursts within a ten-second window.
- **AI-F-023** Produce a grounded explanation with supporting source line numbers and evidence refs.
- **AI-F-024** Count unsupported lines without persisting their content in the result or events.
- **AI-F-025** Make exact analysis retries idempotent and allow only one analysis per request.
- **AI-F-026** Provide create, detail, filtered list, pagination, RBAC, audit, and outbox evidence.
- **AI-NF-008** Limit a batch to 256,000 encoded bytes and a timeline to seven days.
- **AI-NF-009** Keep parsing, redaction, clustering, and anomaly detection deterministic and local.
- **AI-NF-010** Never claim causality solely from log severity, frequency, or temporal proximity.

## IX-4 functional requirements

- **AI-F-027** Create one deterministic test suggestion only for a governed `test_suggestion` request.
- **AI-F-028** Require at least one bounded requirement reference and preserve governed evidence refs.
- **AI-F-029** Store a bounded catalog-compatible candidate as a non-executable draft.
- **AI-F-030** Require an explicit versioned human approval or rejection with a review comment.
- **AI-F-031** Preserve reviewer, timestamp, decision, and rejection rationale as audit evidence.
- **AI-F-032** Allow promotion only after approval and create the catalog definition as `draft`.
- **AI-F-033** Never activate, schedule, or execute a generated test automatically.
- **AI-F-034** Make creation, review, and promotion retries idempotent with stable conflicts.
- **AI-F-035** Provide create, review, promotion, detail, filtered list, RBAC, audit, and outbox APIs.
- **AI-NF-011** Generate suggestions locally without a model, paid API, network call, or GPU.
- **AI-NF-012** Keep audit and outbox payloads free of candidate steps, objectives, and review text.
- **AI-NF-013** Preserve traceability from request and requirements through the promoted definition.

## Verification catalogue

- **AI-T-001** Validate task, subject, identifier, context, and evidence bounds.
- **AI-T-002** Verify default local-only behavior.
- **AI-T-003** Reject restricted data with external-allowed policy.
- **AI-T-004** Verify exact replay and changed-input conflict.
- **AI-T-005** Verify minimized audit and outbox evidence.
- **AI-T-006** Verify explicit RBAC permissions and OpenAPI routes.
- **AI-T-007** Apply migration 0057 through Docker integration.
- **AI-T-008** Verify deterministic DTC, failure-count, and threshold rules and no-match behavior.
- **AI-T-009** Verify queued, running, succeeded, and failed lifecycle outcomes.
- **AI-T-010** Verify retry bounds, execution replay, and stable identifier conflicts.
- **AI-T-011** Reject disabled adapters and policy-invalid external processing.
- **AI-T-012** Verify structured cited output and minimized audit/outbox evidence.
- **AI-T-013** Verify execution APIs, RBAC, pagination, and OpenAPI contracts.
- **AI-T-014** Apply migration 0059 through hosted Docker integration.
- **AI-T-015** Verify supported parsing, timezone ordering, warning normalization, and rejected counts.
- **AI-T-016** Verify email, credential, token, and VIN sanitization before storage.
- **AI-T-017** Verify stable clustering across changing identifiers and numeric values.
- **AI-T-018** Verify severe-event and ten-second burst anomaly evidence.
- **AI-T-019** Verify explanations cite line numbers and governed evidence with explicit limitations.
- **AI-T-020** Verify input bounds, seven-day span, unsupported tasks, replay, and conflicts.
- **AI-T-021** Verify APIs, RBAC, pagination, source filters, and minimized audit/outbox payloads.
- **AI-T-022** Apply migration 0060 and the complete flow through hosted Docker integration.
- **AI-T-023** Verify requirement and evidence bounds plus deterministic candidate generation.
- **AI-T-024** Verify create replay, changed-input conflict, task policy, and one-per-request behavior.
- **AI-T-025** Verify versioned approval and rejection with preserved reviewer evidence.
- **AI-T-026** Reject promotion from draft or rejected states and stale versions.
- **AI-T-027** Verify approved promotion creates only a draft catalog definition.
- **AI-T-028** Verify promotion replay and changed definition identifiers remain safe.
- **AI-T-029** Verify APIs, RBAC, pagination, status filters, and minimized integration evidence.
- **AI-T-030** Apply migration 0061 and the complete workflow through hosted Docker integration.
