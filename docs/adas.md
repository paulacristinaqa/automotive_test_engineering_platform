# ADAS World Model

Volume VII begins with a deterministic, sensor-independent representation of the road scene. This ground truth is the reference against which future camera, radar, LiDAR, perception, and planning results will be evaluated.

## API baseline

- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/advance`
- `PATCH /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/context`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/{result_id}`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/{result_id}/planning-evaluations`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/{result_id}/planning-evaluations/{evaluation_id}`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/{result_id}/test-scenarios`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/{result_id}/test-scenarios`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/sensors/{sensor_id}/observations/{observation_id}/perception-results/{result_id}/test-scenarios/{execution_id}`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/test-scenarios/{execution_id}/integration-evidence`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/test-scenarios/{execution_id}/integration-evidence`

Reads require `adas:read`; mutations require `adas:manage`. A scene uses an ENU coordinate frame, road and lane geometry, one ego vehicle, and bounded ground-truth actors. Advance operations apply constant velocity for a bounded logical duration and require the current revision.

Ground truth answers what exists and where it is; future sensor modules answer what a sensor observed. This boundary makes false positives, false negatives, localization error, latency, and occlusion measurable.

VII-2 adds weather, precipitation, visibility, ambient illumination, temperature, wind, road friction, traffic lights and signs, plus absolute logical-time trajectories. Context changes use the same optimistic revision contract as motion. Trajectory interpolation uses scene logical time, so repeated isolated runs remain reproducible and independent of wall-clock scheduling.

No paid service is required. PostgreSQL persists scenes, while the existing audit and transactional outbox mechanisms provide traceability and integration events.

VII-3 derives camera, radar, and LiDAR observations from a fixed scene revision. The simulator applies mount pose, range, horizontal field of view, environmental visibility, angular occlusion, latency metadata, deterministic seed-based position noise, and sensor-sensitive confidence. Observations are persisted separately from scene truth, allowing later perception scoring and exact evidence retrieval.

VII-4 accepts perception outputs for objects, pedestrians, lanes, signs, and signals. Predictions reference stable truth identifiers and classifications. A one-to-one matcher produces true-positive, false-positive, and false-negative counts plus precision, recall, and F1 overall and by target type. Actor truth is limited to the persisted sensor observation; lane and traffic-control truth comes from the same scene revision. Scoring is rejected if that scene has changed, preventing comparison with stale truth.

VII-5 evaluates deterministic planning decisions from a persisted perception result. Only perceived actors participate in forward-path collision and following-distance calculations. The planner also measures ego offset from the declared lane centerline and consumes perceived red-signal state. Bounded TTC, following-distance, and lane-margin thresholds produce risk metrics, ordered alerts, and one of five maneuvers: maintain lane, lane centering, brake, emergency brake, or stop. Scene, perception, and command revisions must agree before evidence is persisted.

VII-6 turns the verified pipeline into repeatable test evidence. Four scenario families cover car-to-car AEB, pedestrian AEB, lane support, and traffic-signal compliance. A scenario may drop or misclassify selected perception predictions in memory while the authoritative scene, sensor observation, and stored perception result remain unchanged. Explicit maneuver, alert, and F1 assertions determine pass or fail status. Coverage records the exercised target, alert, maneuver, and fault dimensions, while a deterministic SHA-256 fingerprint makes regression comparisons independent from execution identifiers and wall-clock time. These cases are inspired by consumer safety assessment concerns; they are not official NCAP certification procedures.

VII-7 closes the Volume VII baseline with one evidence bundle per ADAS scenario. The bundle links an ATEP test run, existing Vehicle Gateway telemetry and commands, and bounded CarSystemUI display observations for the same vehicle and persisted scenario result. It stores references rather than copying gateway payloads. A compact dashboard summary is persisted with the bundle and published after commit on the existing authenticated test-run Redis/WebSocket channel. Redis failure affects only the live update; the durable database, audit, and outbox evidence remains authoritative.
