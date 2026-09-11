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

Requirements DASH-F-001 through DASH-F-012 and DASH-NF-001 through DASH-NF-011 are implemented
through X-3. Visual clients and historical materialization are outside this increment.
