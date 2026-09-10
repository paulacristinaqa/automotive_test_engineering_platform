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

## Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| DASH-NF-001 | Dashboard access shall require `dashboard:read`. | Permission catalogue and router |
| DASH-NF-002 | Query windows shall be limited to 720 hours. | OpenAPI contract test |
| DASH-NF-003 | Evidence cards shall be limited to 50 per request. | OpenAPI contract test |
| DASH-NF-004 | The read model shall not mutate source records or emit events. | Read-only service design |
| DASH-NF-005 | KPI ordering and rounding shall be deterministic. | Unit tests |
| DASH-NF-006 | The increment shall require no paid service or GPU. | Local architecture |

## Traceability status

Requirements DASH-F-001 through DASH-F-006 and DASH-NF-001 through DASH-NF-006 are implemented
in X-1. Visual clients and historical materialization are outside this increment.
