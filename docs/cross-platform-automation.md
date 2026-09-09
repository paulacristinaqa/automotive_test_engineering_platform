# Cross-platform Automation Reporting

Volume VIII-7 closes the functional Test Framework baseline by correlating evidence already produced
by ATEP, Vehicle Gateway, and CarSystemUI. The report is a durable final record, not a new transport
or generic command runner.

## Evidence flow

1. ATEP creates and completes a vehicle-scoped test run.
2. The selected gateway publishes telemetry and consumes authorized leased commands.
3. Optional fault and mutation executions complete under the same test run.
4. CarSystemUI records the authoritative run status and version it displayed.
5. An authorized engineer creates the report with stable evidence identifiers.
6. ATEP validates every relationship, derives the combined outcome, and commits report, audit, and outbox evidence atomically.

## Consistency rules

- the test run must be passed, failed, or cancelled and belong to the selected vehicle;
- the gateway must declare both telemetry publishing and command consumption capabilities;
- telemetry must originate from that vehicle and gateway;
- commands must be terminal and belong to that vehicle, gateway, and test run;
- optional fault and mutation executions must be terminal and belong to that vehicle and test run;
- CarSystemUI observations must be timezone-aware and display the persisted run status and version;
- each test run can have only one final report, and an exact request retry is idempotent.

## Outcome precedence

The report is failed when any correlated execution failed. If nothing failed but one component was
cancelled, the report is cancelled. Otherwise it is passed. The summary preserves the test-run
version, optional execution statuses, mutation score, and evidence counts.

## Security and resource bounds

Reads require `test_catalog:read`; creation requires `test_catalog:manage`. A report contains at
most 100 telemetry identifiers, 100 command identifiers, and 50 CarSystemUI observations. Detailed
collections remain in PostgreSQL; audit and outbox messages publish only bounded identifiers,
statuses, and counts. The feature requires no GPU, paid cloud service, or paid AI API.

## Verification objectives

- validate the complete correlated happy path and exact retry;
- reject missing, nonterminal, cross-vehicle, cross-gateway, and cross-run references;
- reject stale CarSystemUI views and timestamps without a UTC offset;
- verify outcome precedence, summaries, RBAC, pagination, audit, and outbox atomicity;
- verify migration 0056 and the full disposable PostgreSQL, Redis, RabbitMQ, and WebSocket scenario.
