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

## VII-4 Perception and ground-truth scoring

- **ADAS-F-022** Submit persisted perception results for an exact sensor observation.
- **ADAS-F-023** Represent object, pedestrian, lane, sign, and signal predictions.
- **ADAS-F-024** Associate predictions with stable ground-truth identifiers and classifications.
- **ADAS-F-025** Score predictions one-to-one as true positives, false positives, and false negatives.
- **ADAS-F-026** Calculate deterministic precision, recall, and F1 overall and by target type.
- **ADAS-F-027** Expose perception result creation and retrieval APIs.
- **ADAS-NF-009** Reject scoring when the current scene revision differs from the observation revision.
- **ADAS-NF-010** Keep operational evidence free from complete prediction payloads.

- **ADAS-T-035** Reject duplicate prediction identifiers and out-of-range confidence.
- **ADAS-T-036** Verify object and pedestrian truth is limited to actors present in the observation.
- **ADAS-T-037** Verify lane truth is derived from the authoritative road model.
- **ADAS-T-038** Verify sign and signal truth includes type-specific classifications and state.
- **ADAS-T-039** Verify perfect predictions produce precision, recall, and F1 of one.
- **ADAS-T-040** Verify duplicate predictions cannot match one truth item twice.
- **ADAS-T-041** Verify misclassification produces one false positive and one false negative.
- **ADAS-T-042** Reject scoring after scene truth changes with `adas_scene_version_conflict`.
- **ADAS-T-043** Verify `adas:read` and `adas:manage` protection on perception APIs.
- **ADAS-T-044** Verify atomic, minimized audit and `atep.adas.perception.result.created.v1` evidence.

## VII-5 Planning and alerts

- **ADAS-F-028** Evaluate a planning decision from a persisted perception result and exact scene revision.
- **ADAS-F-029** Calculate nearest lead-vehicle distance and minimum time to collision for perceived actors.
- **ADAS-F-030** Measure ego lateral distance from the declared lane centerline.
- **ADAS-F-031** Detect unsafe following distance, lane departure, forward collision risk, and red signals.
- **ADAS-F-032** Select maintain-lane, lane-centering, brake, emergency-brake, or stop maneuvers deterministically.
- **ADAS-F-033** Persist risk metrics, maneuver, alerts, input thresholds, audit, and outbox evidence.
- **ADAS-F-034** Expose planning evaluation creation and retrieval APIs.
- **ADAS-NF-011** Bound thresholds and require emergency-brake TTC below collision-warning TTC.
- **ADAS-NF-012** Use only actors represented in perception output for actor-based planning risks.
- **ADAS-NF-013** Reject planning when scene, perception, and command revisions do not match.

- **ADAS-T-045** Reject invalid or unordered planning thresholds.
- **ADAS-T-046** Verify a safe scene produces maintain-lane with no alerts.
- **ADAS-T-047** Verify TTC uses relative forward speed and the nearest collision-path actor.
- **ADAS-T-048** Verify critical forward-collision risk selects emergency braking.
- **ADAS-T-049** Verify short lead distance produces an unsafe-following alert.
- **ADAS-T-050** Verify lateral lane-envelope violation selects lane centering.
- **ADAS-T-051** Verify a perceived red signal selects stop.
- **ADAS-T-052** Verify maneuver priority is deterministic when multiple risks exist.
- **ADAS-T-053** Reject unknown ego lane and changed scene revisions.
- **ADAS-T-054** Verify `adas:read` and `adas:manage` protection on planning APIs.
- **ADAS-T-055** Verify atomic, minimized audit and `atep.adas.planning.evaluation.created.v1` evidence.

## VII-6 ADAS test scenarios

- **ADAS-F-035** Execute persisted NCAP-inspired car-to-car AEB, pedestrian AEB, lane-support, and traffic-signal scenario families.
- **ADAS-F-036** Apply bounded prediction-drop and prediction-misclassification faults without changing scene truth or stored perception evidence.
- **ADAS-F-037** Evaluate expected maneuver, required alerts, and minimum overall perception F1 as explicit assertions.
- **ADAS-F-038** Persist pass or fail status, observed maneuver, alerts, assertion evidence, fault inputs, and per-execution coverage.
- **ADAS-F-039** Generate a deterministic SHA-256 regression fingerprint independent from execution identity and wall-clock time.
- **ADAS-F-040** Provide exact idempotent replay and reject changed reuse of an execution identifier with a stable conflict.
- **ADAS-F-041** Expose execute, bounded list, and detail APIs protected by ADAS permissions.
- **ADAS-F-042** Atomically record audit and transactional outbox evidence for completed scenarios.
- **ADAS-NF-014** Limit each execution to twenty unique fault targets and four unique required alert types.
- **ADAS-NF-015** Reject unknown fault targets and stale scene or perception revisions before persistence.
- **ADAS-NF-016** Keep events free from complete predictions, alerts, assertion details, and fault payloads.
- **ADAS-NF-017** Describe scenarios as NCAP-inspired engineering exercises, not official homologation or certification evidence.

- **ADAS-T-056** Reject malformed fault definitions, duplicate fault targets, duplicate alerts, and invalid thresholds.
- **ADAS-T-057** Verify the car-to-car AEB family passes for a perceived imminent lead-vehicle collision.
- **ADAS-T-058** Verify dropping a critical perception prediction changes planner output and fails the expected assertions.
- **ADAS-T-059** Verify misclassification changes only the selected prediction and preserves stored perception evidence.
- **ADAS-T-060** Reject fault injection against an unknown prediction before any write.
- **ADAS-T-061** Verify assertion status and assertion-coverage counts for passed and failed scenarios.
- **ADAS-T-062** Verify different execution identifiers with identical deterministic inputs produce the same regression fingerprint.
- **ADAS-T-063** Verify exact replay is idempotent and changed identifier reuse returns `adas_scenario_execution_conflict`.
- **ADAS-T-064** Reject stale scene and perception revisions before scenario evidence is stored.
- **ADAS-T-065** Verify bounded, stable newest-first scenario pagination.
- **ADAS-T-066** Verify `adas:read`, `adas:manage`, and HTTP 403 behavior for scenario APIs.
- **ADAS-T-067** Verify atomic audit and `atep.adas.test_scenario.completed.v1` evidence is minimized.
- **ADAS-T-068** Verify migration `0049` upgrade and downgrade structure.
