# Volume II requirements — Digital Vehicle

## Functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| DV-F-001 | Every vehicle shall own exactly one digital-state aggregate. | Model, migration, registration test |
| DV-F-002 | The aggregate shall represent operational mode, battery, powertrain, brakes, steering, and lighting. | Typed schemas and OpenAPI |
| DV-F-003 | Vehicle registration shall create a deterministic safe baseline. | Service and tests |
| DV-F-004 | Authorized clients shall read and replace the complete state through versioned HTTP APIs. | GET/PUT API tests |
| DV-F-005 | Replacement shall validate component bounds and cross-component safety invariants. | Schema tests |
| DV-F-006 | Replacement shall use optimistic version control and report stale updates with a stable conflict error. | Service and integration tests |
| DV-F-007 | An exact retry shall be idempotent and shall not duplicate transition evidence. | Retry test |
| DV-F-008 | A real transition shall atomically persist state, audit evidence, and a versioned outbox event. | Transaction test |
| DV-F-009 | Simulation time shall advance only by an explicitly commanded bounded duration. | Deterministic sequence test |
| DV-F-010 | The initial transition engine shall enforce `parked → ready → driving → parked`. | State-machine tests |
| DV-F-011 | Simulation commands shall be vehicle-scoped and idempotent by command identifier. | Retry and conflict tests |
| DV-F-012 | Accepted transitions shall persist replay metadata and atomic audit/outbox evidence. | Service and integration tests |
| DV-F-013 | Simulation steps shall model bounded accelerator, brake, and steering actuator inputs. | Contract and deterministic-step tests |
| DV-F-014 | Speed, battery SOC, and battery-temperature sensors shall support seeded noise and explicit stuck/offset fault modes. | Seed replay and fault tests |
| DV-F-015 | Simulation steps shall be vehicle-scoped, versioned, idempotent, and persisted for replay. | Retry, conflict, migration, and evidence tests |
| DV-F-016 | Driving steps shall calculate bounded energy use, regenerative recovery, usable battery energy, and SOC. | Conservation and braking scenario tests |
| DV-F-017 | Thermal behavior shall combine load generation, ambient cooling, and absolute temperature bounds. | Hot/cold boundary and scenario tests |
| DV-F-018 | Road grade, roughness, steering, braking, and ambient light shall influence powertrain, suspension, lateral response, and lighting deterministically. | Coupled drive-corner-brake scenario |
| DV-F-019 | A simulation session shall contain 1–20 unique registered vehicles. | Contract and creation tests |
| DV-F-020 | Session snapshots shall store member states in canonical vehicle order with a SHA-256 content digest. | Canonical snapshot test |
| DV-F-021 | Snapshot restore shall lock members deterministically, restore only matching vehicle state, preserve logical time, and increment versions. | Isolation and restore test |

## Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| DV-NF-001 | Read and write access shall use independent deny-by-default permissions. | RBAC tests |
| DV-NF-002 | Numeric inputs shall have explicit safe contract bounds. | Pydantic schema tests |
| DV-NF-003 | Error responses shall use the platform-wide correlation-aware envelope. | API contract tests |
| DV-NF-004 | Audit details shall avoid copying the complete state payload. | Audit assertions |
| DV-NF-005 | The migration shall backfill existing vehicles without requiring cloud infrastructure. | Alembic and disposable integration |
| DV-NF-006 | The increment shall pass Ruff, strict mypy, unit/contract tests, and disposable integration. | CI quality gates |
| DV-NF-007 | Deterministic simulation shall not depend on wall-clock time, timers, background loops, GPU, or cloud infrastructure. | Design and tests |
| DV-NF-008 | Equal state, command, and seed inputs shall produce equal sensor readings across runs. | Deterministic seed test |
| DV-NF-009 | Published energy evidence shall satisfy `used - recovered = net` at contract precision and recovery shall never exceed bounded consumption. | Conservation assertions |
| DV-NF-010 | Session creation, snapshot, and restore shall produce atomic bounded audit and outbox evidence without background loops. | Transaction assertions |
