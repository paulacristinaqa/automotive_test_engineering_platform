# Volume X Dashboard Requirements

## Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-001 | The platform shall expose an authenticated dashboard overview. | `GET /api/v1/dashboard/overview` |
| DASH-F-002 | The overview shall aggregate test-run and case-result status counts. | Dashboard service and tests |
| DASH-F-003 | The overview shall calculate case pass rate without dividing by zero. | `test_dashboard.py` |
| DASH-F-004 | The overview shall expose current requirement coverage and rate. | Dashboard service and tests |
| DASH-F-005 | The overview shall summarize mutation, automation, and dashboard AI evidence. | Dashboard service and tests |
| DASH-F-006 | Recent AI cards shall preserve citations and exclude source context. | Response schema and service |
| DASH-F-007 | The platform shall expose complete UTC daily test-quality buckets for a bounded historical window. | Trends service and tests |
| DASH-F-008 | Each trend bucket shall expose run outcomes, case outcomes, and truthful pass-rate semantics. | Trend calculation tests |
| DASH-F-009 | The platform shall expose failed case results with run, definition, suite, duration, observation, and evidence references. | Failure drill-down API |
| DASH-F-010 | Failure results shall support bounded pagination, time window, and suite filtering. | OpenAPI and integration tests |

## X-3 operational requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-011 | Expose current vehicle, ECU, session and stored-DTC distributions. | Operations service and aggregate tests |
| DASH-F-012 | Distinguish CAN inventory from time-windowed CAN and diagnostic activity. | Independent SQL aggregates and integration |
| DASH-NF-010 | Operations require dashboard:read and reject windows outside 1–720 hours. | Integration 403/422 and OpenAPI tests |
| DASH-NF-011 | Exclude memory, keys, command payloads and diagnostic snapshots. | Explicit column selection and response schema |

## Non-functional requirements

### X-4 mobility requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-013 | Expose SOC/SOH and component temperature distributions with units and sample counts. | Mobility projection and unit tests |
| DASH-F-014 | Expose battery, motor, charging and thermal source-state distributions. | Mobility aggregate queries |
| DASH-F-015 | Expose windowed EV/ADAS scenario outcomes and ADAS planning maneuvers. | SQL boundary tests |
| DASH-NF-012 | Empty numeric populations shall return null statistics, not invented zeros. | Empty-state tests |
| DASH-NF-013 | Mobility access requires dashboard:read and windows of 1–720 hours. | OpenAPI and integration 403/422 checks |

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-001 | Dashboard access shall require `dashboard:read`. | Permission catalogue and router |
| DASH-NF-002 | Query windows shall be limited to 720 hours. | OpenAPI contract test |
| DASH-NF-003 | Evidence cards shall be limited to 50 per request. | OpenAPI contract test |
| DASH-NF-004 | The read model shall not mutate source records or emit events. | Read-only service design |
| DASH-NF-005 | KPI ordering and rounding shall be deterministic. | Unit tests |
| DASH-NF-006 | The increment shall require no paid service or GPU. | Local architecture |
| DASH-NF-007 | Trend responses shall contain no more than 90 daily buckets. | Query contract |
| DASH-NF-008 | Failure observations shall expose no more than 500 characters. | Mapping tests |
| DASH-NF-009 | Empty daily buckets and undefined rates shall remain explicit. | Trend tests |

## Traceability status

### X-6.2 live snapshot requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-019 | Stream versioned periodic snapshots for three allowlisted views with server-query freshness metadata. | WebSocket integration and frame tests |
| DASH-NF-019 | Revalidate token, active user and dashboard permission before generating and sending each snapshot. | Auth and revocation tests |
| DASH-NF-020 | Bound admitted connections per process, snapshot count, refresh interval and send duration. | Capacity, periodic and slow-consumer tests |
| DASH-NF-021 | Release connection capacity on disconnect or failure; accept no client refresh commands or URL tokens. | Cleanup and read-only tests |

### X-6.1 export requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-018 | Export three allowlisted aggregate dashboard views as versioned JSON attachments. | Router, schema, integration |
| DASH-NF-016 | Exports require dashboard:read and 1–720-hour windows. | OpenAPI and HTTP 403/422 integration |
| DASH-NF-017 | Do not persist export artifacts; instruct HTTP caches not to store responses. | Service design and response-header tests |
| DASH-NF-018 | Apply cooperative generation timeout and serialized-byte limit with stable errors. | Cancellation and exact-size boundary tests |

### X-5 approved supporting-evidence scope

| ID | Requirement | Evidence |
|---|---|---|
| DASH-F-016 | Summarize current diagnostic flash and requirement coverage states plus windowed administrative audit outcomes. | Evidence aggregation service |
| DASH-F-017 | Expose four explicit gap cards with source identifiers, missing capabilities and limitations. | Empty/populated unit tests |
| DASH-NF-014 | Keep assessment not_assessed regardless of evidence volume; do not compute conformity/readiness percentages. | Literal schema and unit tests |
| DASH-NF-015 | Enforce dashboard:read, 1–720-hour windows and aggregate-only data selection. | OpenAPI, SQL and integration tests |

These requirements implement the approved reduced X-5 scope. Formal standards mappings and
OTA lifecycle capabilities are deferred, not certified or inferred from generic evidence.

Requirements DASH-F-001 through DASH-F-015 and DASH-NF-001 through DASH-NF-013 are implemented
through X-4. Visual clients and historical materialization are outside this increment.
