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

## VII-3 Deterministic sensor simulation

- **ADAS-F-014** Configure camera, radar, and LiDAR sensors for a scene without changing scene truth.
- **ADAS-F-015** Bound sensor mount, yaw, range, horizontal field of view, latency, and position noise.
- **ADAS-F-016** Produce persisted observations tied to an exact scene revision and logical time.
- **ADAS-F-017** Filter actors by effective visibility range and sensor field of view.
- **ADAS-F-018** Apply deterministic angular occlusion using nearer visible actors.
- **ADAS-F-019** Apply seed-derived position noise and environment-sensitive confidence.
- **ADAS-F-020** Expose sensor creation, listing, observation capture, and observation retrieval APIs.
- **ADAS-F-021** Atomically record audit and outbox evidence for sensors and observations.
- **ADAS-NF-007** Repeating an observation from identical truth, configuration, and seed shall produce identical detections.
- **ADAS-NF-008** Operational events shall contain counts and references, not complete detection payloads.

- **ADAS-T-023** Reject invalid range, field of view, latency, noise, and identifiers.
- **ADAS-T-024** Verify an actor outside the field of view is excluded.
- **ADAS-T-025** Verify an actor beyond effective visibility or sensor range is excluded.
- **ADAS-T-026** Verify a nearer aligned actor occludes a farther actor.
- **ADAS-T-027** Verify identical seeds produce identical noise and different seeds vary it.
- **ADAS-T-028** Verify camera confidence responds to precipitation and low light.
- **ADAS-T-029** Verify LiDAR confidence responds to fog, rain, and snow while radar remains available.
- **ADAS-T-030** Reject capture against a stale scene revision.
- **ADAS-T-031** Verify observation latency, captured scene time, and revision are persisted.
- **ADAS-T-032** Verify sensor and observation identity conflicts are stable.
- **ADAS-T-033** Verify `adas:read` and `adas:manage` protection on all sensor APIs.
- **ADAS-T-034** Verify atomic, minimized audit and outbox evidence.
