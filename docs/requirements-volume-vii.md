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

## VII-2 Environment and traffic controls

- **ADAS-F-008** Store weather, precipitation, visibility, illumination, temperature, wind, and road friction as scene ground truth.
- **ADAS-F-009** Store traffic lights, stop signs, yield signs, and speed-limit signs with lane references.
- **ADAS-F-010** Replace scene context only when the expected scene revision matches.
- **ADAS-F-011** Support actor trajectories as ordered absolute logical-time waypoints.
- **ADAS-F-012** Interpolate actor positions deterministically between trajectory waypoints.
- **ADAS-F-013** Continue from a final waypoint using its declared velocity, or hold position when none is declared.
- **ADAS-NF-005** Reject inconsistent weather, traffic controls, lane references, and trajectory timelines.
- **ADAS-NF-006** Keep context events minimized and free from complete road or actor collections.

- **ADAS-T-013** Reject rain or snow without positive precipitation.
- **ADAS-T-014** Reject fog visibility above the configured fog bound.
- **ADAS-T-015** Reject traffic controls that reference unknown lanes.
- **ADAS-T-016** Reject missing type-specific traffic control fields.
- **ADAS-T-017** Reject duplicate traffic control identifiers.
- **ADAS-T-018** Reject trajectories that do not start at zero or are not strictly ordered.
- **ADAS-T-019** Verify deterministic interpolation at an intermediate logical time.
- **ADAS-T-020** Verify behavior after the final waypoint with and without terminal velocity.
- **ADAS-T-021** Verify stale context updates do not mutate the scene.
- **ADAS-T-022** Verify atomic audit and `atep.adas.world_scene.context_updated.v1` evidence.
