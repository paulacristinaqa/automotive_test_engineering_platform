# AI Test Engineer Foundation

Volume IX begins with an orchestration and governance boundary, not an embedded paid model. ATEP
stores immutable, provider-neutral analysis requests. Workers and result contracts follow in IX-2.

## Contract

`POST /api/v1/ai/analysis-requests` records a task, one supported subject, evidence references,
bounded structured context, optional instructions, provider policy, and data classification. GET
collection and detail endpoints expose the resulting queued request.

The supported tasks are log analysis, failure explanation, test suggestion, root cause, and risk
analysis. Subjects may be a test run, automation report, fault execution, or mutation execution.

## Privacy and cost controls

`local_only` is the default. Restricted data cannot use `external_allowed`. IX-1 performs no model
call, requires no API key, downloads no model, and uses no GPU. Audit and outbox records carry only
identity and count metadata. Raw context and instructions remain inside the access-controlled record.

AI recommendations are advisory. They cannot issue vehicle commands, mutate test results, or promote
generated tests without a later explicit review workflow.
