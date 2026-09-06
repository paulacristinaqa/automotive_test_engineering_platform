# ADAS World Model

Volume VII begins with a deterministic, sensor-independent representation of the road scene. This ground truth is the reference against which future camera, radar, LiDAR, perception, and planning results will be evaluated.

## API baseline

- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes`
- `GET /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}`
- `POST /api/v1/vehicles/{vehicle_id}/adas/scenes/{scene_id}/advance`

Reads require `adas:read`; mutations require `adas:manage`. A scene uses an ENU coordinate frame, road and lane geometry, one ego vehicle, and bounded ground-truth actors. Advance operations apply constant velocity for a bounded logical duration and require the current revision.

Ground truth answers what exists and where it is; future sensor modules answer what a sensor observed. This boundary makes false positives, false negatives, localization error, latency, and occlusion measurable.

No paid service is required. PostgreSQL persists scenes, while the existing audit and transactional outbox mechanisms provide traceability and integration events.
