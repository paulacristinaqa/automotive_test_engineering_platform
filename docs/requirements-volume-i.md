# Volume I requirements

## Functional requirements

| ID | Requirement | Initial verification |
|---|---|---|
| CORE-F-001 | The platform shall authenticate an active user and issue a time-limited token. | API test |
| CORE-F-002 | The platform shall authorize operations using role permissions. | Unit/API test |
| CORE-F-003 | The platform shall persist identity and outbox state in PostgreSQL. | Automated Docker integration test |
| CORE-F-004 | The platform shall publish versioned domain events to RabbitMQ. | Automated Docker integration test |
| CORE-F-005 | The platform shall expose liveness and dependency readiness. | API test |
| CORE-F-006 | The platform shall attach a correlation ID to requests and responses. | API test |
| CORE-F-007 | The platform shall create the first administrator only from explicit bootstrap configuration. | Automated Docker integration test |
| CORE-F-008 | An authorized administrator shall create, list, inspect, activate, and deactivate users and manage their role assignments. | API/service test |
| CORE-F-009 | Security-relevant identity changes shall create immutable audit records containing actor, action, resource, correlation, and non-sensitive details. | Service/database test |
| CORE-F-010 | User creation shall persist the user and `atep.identity.user.created.v1` outbox event atomically. | Automated Docker integration test |
| CORE-F-011 | API failures shall use one stable error envelope with a correlation identifier. | API contract test |
| CORE-F-012 | Successful authentication shall issue a short-lived access token and a longer-lived opaque refresh token. | Automated Docker integration test |
| CORE-F-013 | Refresh-token use shall atomically invalidate the presented token and issue a new token pair. | Automated Docker integration test |
| CORE-F-014 | Reuse of a rotated refresh token shall revoke every active token in the same family. | Automated Docker integration test |
| CORE-F-015 | A user shall revoke one refresh-token family or all of their renewable sessions. | Automated Docker integration test |
| CORE-F-016 | An authorized administrator shall list, create, inspect, update, and safely delete roles and manage their permission grants. | API/service and automated Docker integration test |
| CORE-F-017 | The platform shall protect the `platform-admin` role from renaming, permission removal, and deletion, and reject deletion of roles assigned to users. | Negative API and automated Docker integration test |
| CORE-F-018 | An authorized investigator shall search and inspect immutable audit records using bounded pagination and indexed filters, while a separately authorized user may export a bounded CSV whose creation is itself audited. | API, service, and automated Docker integration test |
| CORE-F-019 | The platform shall enforce distributed Redis-backed limits for authentication and versioned API requests and return stable retry metadata when a limit is exceeded. | Unit and automated Docker integration test |
| CORE-F-020 | An authorized administrator shall register, inspect, page, filter, and update ATEP modules and declare or remove their versioned capabilities. | API, service, and automated Docker integration test |
| CORE-F-021 | Module registration and effective catalogue mutations shall append correlated immutable audit evidence and versioned transactional outbox events. | Service/database and automated Docker integration test |
| CORE-F-022 | An authorized administrator shall issue or rotate a module workload credential whose raw value is returned once and whose SHA-256 digest is the only persisted representation. | Service and automated Docker integration test |
| CORE-F-023 | An authenticated module shall renew a bounded availability lease through heartbeat, while automatic reconciliation shall mark an expired module inactive and record the transition. | Unit, API contract, and automated Docker integration test |

## Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| CORE-NF-001 | API availability | 99.9% after production deployment |
| CORE-NF-002 | API latency | p95 under 250 ms excluding long-running test operations |
| CORE-NF-003 | Event delivery | at-least-once with retry and idempotent consumers |
| CORE-NF-004 | Security | Argon2 credentials, least privilege, no committed secrets |
| CORE-NF-005 | Observability | structured logs and end-to-end correlation IDs |
| CORE-NF-006 | Maintainability | module boundaries, typed code, automated lint/test gates |
| CORE-NF-007 | Data protection | passwords and password hashes never appear in API responses, event payloads, audit details, or application logs |
| CORE-NF-008 | Integration repeatability | isolated ports, ephemeral credentials, disposable data, automatic cleanup, and CI execution |
| CORE-NF-009 | Refresh-token protection | raw refresh tokens are returned once, only SHA-256 hashes are persisted, and security actions are audited without token material |
| CORE-NF-010 | Role-catalogue integrity | role names are canonical and unique, mutations are auditable, pagination is bounded, and protected-role invariants cannot be bypassed through the API |
| CORE-NF-011 | Audit evidence lifecycle | audit records remain immutable, are retained online for at least 365 days, are archived for at least seven years unless policy requires longer, and are never purged while subject to legal hold |
| CORE-NF-012 | Abuse-control consistency | rate-limit counters are atomic, expire automatically, store no raw email, address, or credential, and fail closed with a controlled response when Redis is unavailable |
| CORE-NF-013 | Module-catalogue integrity | module and capability names are canonical and unique in scope, versions follow semantic-version syntax, pagination is bounded, and read/manage permissions are independent |
| CORE-NF-014 | Operational-registry integrity | raw workload credentials never enter persistence or evidence, operational states are heartbeat-controlled, leases are bounded, and expiry transitions are evented and audited |
