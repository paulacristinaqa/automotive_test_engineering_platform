# X-7.15 — AAOS active-user deactivation

Status: real-device scenario passed on 2026-09-16.

## Scenario and isolation

A separate disposable account receives only `dashboard:read` and a normal
five-minute access token. Android establishes a LIVE session with a longer
600-second local budget. Only its exact `inactive-ready` checkpoint allows the
host to PATCH that fixture user's status to `is_active: false`.

The host verifies the account is inactive while its dashboard permission remains
assigned, and checks that the same token now receives HTTP 401 /
`invalid_credentials`. It starts this mutation within 220 seconds of issuance
and finishes its probes before 230 seconds. Android must reach AUTH_REQUIRED
within 65 seconds of its checkpoint, before either JWT or local expiry can
explain the result. The regular server reauthorization interval is unchanged;
this is not instantaneous push revocation.

The device checks an empty credential field, no envelope in the accessible tree
and a stable terminal state after a short observation. It retains a local
screenshot only after those assertions. This is interface cleanup, not proof of
whole-process memory erasure or indefinite absence of network traffic.

## Safety and coordinator tests

Only the newly created fixture account is disabled; no existing user is changed.
Administrator credentials stay on the host. The shared fixture role is not
deleted or altered, so other acceptance accounts retain their permissions.
Missing, early, duplicate or failed checkpoints cannot pass, and the following
server-expiry probe cannot run before deactivation has been confirmed.

Six additional coordinator tests cover successful order, early and duplicate
signals, missing completion, missing deactivation before server expiry and
mutation failure. The coordinator suite now contains 22 tests. The combined
scenario retains its 480-second bound and output/queue limits. No runtime
dependency, paid service, clock manipulation or production policy change is added.

Run using the sequential procedure in `dashboard-aaos-acceptance.md`. Real network
failure/reconnect/staleness, expiry during retry and normal ten-snapshot completion
remain separate gates before trusted-proxy deployment acceptance.

## Evidence

The API 35 driver-user scenario passed: the host observed the exact LIVE
checkpoint, disabled the fixture account, verified its retained dashboard role
and HTTP 401 for the same token. Android reached AUTH_REQUIRED within the bounded
unexpired window, with an empty credential field and no displayed envelope.
The local screenshot `dr-evidence/dashboard-aaos-inactive.png` was inspected.
Basic smoke, initial denial, local expiry, role loss and natural JWT expiry also
passed in the combined run.

All 22 coordinator tests, Ruff and strict mypy passed. Android build/lint completed
in 30 seconds, retaining 57 passing JVM tests and zero lint errors/15 warnings.
Both backend integration tests passed in 20.52 seconds. Sampled CPU was 40–71%,
GPU 13–18%, with 10.4 GiB RAM free in device-stage samples. These are intermittent
observations, not measured peaks or a capacity guarantee. DOCX is unchanged.

PostgreSQL restore passed with 87 tables/310 rows in 81.578 seconds. All 22
coordinator tests passed again in 1.16 seconds; Ruff/mypy and diff checks passed.
The owned emulator and temporary integration containers were confirmed absent
after cleanup; final sampled CPU was 39%. Changes remain local and uncommitted;
no pull request or merge was performed in this increment.
