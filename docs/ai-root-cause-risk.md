# AI Root Cause and Risk

Volume IX-5 provides deterministic investigation priorities and comparable prediction evidence. It
runs locally without a model, API key, network call, cloud account, paid service, or GPU.

## Analysis contract

A governed `root_cause` or `risk_analysis` request accepts up to 50 unique signals. Every signal
contains a code, component, symptom, severity, occurrence count, confidence, detectability, and one
or more evidence references already authorized by the parent request.

Each signal becomes a candidate hypothesis. The support score uses fixed severity weights multiplied
by bounded confidence and occurrence factors. Candidates are ordered by descending support score
and then by code for deterministic tie-breaking. Each hypothesis states that association does not
prove causality and requires engineering review.

## Risk formula

The risk score is rounded and clamped from 0 to 100:

`0.45 * highest hypothesis support + 0.40 * highest severity impact + 0.15 * inverse detectability`

The fixed bands are low below 25, medium from 25 to 49, high from 50 to 74, and critical from 75.
The score prioritizes investigation; it is not a calibrated failure probability or safety decision.

## Prediction evaluation

An authorized evaluation records the observed failure outcome, governed evidence, and optionally a
confirmed hypothesis that was present in the original ranking. A prediction is positive when the
risk score is at least 50. ATEP records correctness and the Brier score `(prediction - outcome)^2`.
Historical metrics expose evaluated count, correct count, accuracy, and mean Brier score.

## Public API

- `POST /api/v1/ai/analysis-requests/{request_id}/root-cause-risk`
- `GET /api/v1/ai/root-cause-risk`
- `GET /api/v1/ai/root-cause-risk/{analysis_id}`
- `POST /api/v1/ai/root-cause-risk/{analysis_id}/evaluation`
- `GET /api/v1/ai/root-cause-risk/prediction-metrics`

Read operations require `ai_analysis:read`; mutations require `ai_analysis:manage`. Audit and outbox
payloads contain aggregate scores and counts, not symptoms, signal collections, hypotheses, or raw
evaluation evidence. No endpoint mutates vehicle, catalog, schedule, or test execution state.
