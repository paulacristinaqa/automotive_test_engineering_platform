# Volume VII ADAS Requirements

## VII-1 Deterministic world model

- **ADAS-F-001** Create a vehicle-scoped ADAS scene in an East North Up coordinate frame.
- **ADAS-F-002** A scene contains roads, globally unique lanes, and exactly one ego vehicle.
- **ADAS-F-003** Ground-truth actors include vehicles, pedestrians, cyclists, and static obstacles.
- **ADAS-F-004** Expose create, paginated list, detail, and deterministic advance operations.
- **ADAS-F-005** Advance actors with constant velocity and logical elapsed time.
- **ADAS-F-006** Require an expected revision and return a stable conflict for stale mutations.
- **ADAS-F-007** Atomically record audit and outbox evidence for create and advance operations.
- **ADAS-NF-001** Limit pages to 1 through 100 and offsets to 1,000,000.
- **ADAS-NF-002** Bound coordinates, dimensions, velocities, geometry, durations, and collections.
- **ADAS-NF-003** Keep ground truth independent from sensor detections.
- **ADAS-NF-004** Run locally without paid cloud or AI services.

## Verification catalogue

- **ADAS-T-001** Accept a valid ENU scene and preserve its ground truth.
- **ADAS-T-002** Reject scenes without exactly one ego vehicle.
- **ADAS-T-003** Reject duplicate road, lane, and actor identifiers.
- **ADAS-T-004** Reject out-of-range geometry, dimensions, durations, and collections.
- **ADAS-T-005** Verify constant-velocity positions after two seconds of logical time.
- **ADAS-T-006** Reject stale revisions before mutation with `adas_scene_version_conflict`.
- **ADAS-T-007** Verify minimized audit and `atep.adas.world_scene.created.v1` evidence.
- **ADAS-T-008** Verify advance evidence includes revision, duration, and logical time.
- **ADAS-T-009** Verify `adas:read`, `adas:manage`, and HTTP 403 behavior.
- **ADAS-T-010** Verify pagination limits through the API contract.
- **ADAS-T-011** Verify database uniqueness and migration upgrade and downgrade.
- **ADAS-T-012** Verify identical isolated inputs produce identical outputs.
