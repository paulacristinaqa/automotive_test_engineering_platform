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

## Verification catalogue

- **AI-T-001** Validate task, subject, identifier, context, and evidence bounds.
- **AI-T-002** Verify default local-only behavior.
- **AI-T-003** Reject restricted data with external-allowed policy.
- **AI-T-004** Verify exact replay and changed-input conflict.
- **AI-T-005** Verify minimized audit and outbox evidence.
- **AI-T-006** Verify explicit RBAC permissions and OpenAPI routes.
- **AI-T-007** Apply migration 0057 through Docker integration.
