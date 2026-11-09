# X-7.22 — Bounded multiprocess admission acceptance

## Purpose

Verify that two independent FastAPI/Uvicorn processes behind the trusted Nginx
boundary consume the **same Redis handshake budget**. This is a sequential
functional acceptance test, not stress testing or a capacity benchmark.

## Architecture and constraints

- Two single-worker API containers share the integration database and Redis.
- Each API is capped at 512 MiB, 0.5 CPU and 64 PIDs. The existing bounded,
  non-root, read-only Nginx fixture is retained.
- Loopback ports 18801 and 18802 deterministically select replica A and B.
  Nginx overwrites forwarding headers and records its actual upstream address
  in a test-only response header, including denied upgrades.
- Container IDs and Docker-host process IDs must be distinct. Inspection also
  verifies the configured resource bounds; it does not print environments.
- Replica B has no host port. Replica A retains loopback port 18000 for the
  existing integration suite. Other base dependency ports are unchanged.
- Replica B starts after replica A is healthy to avoid testing bootstrap races.
  Its periodic module reconciliation is disabled; background-job distribution
  is outside this acceptance scope.
- TLS remains the separate X-7.21 gate. This local HTTP fixture neither repeats
  TLS acceptance nor claims combined multi-replica TLS deployment coverage.

Two explicitly selected processes are used instead of probabilistic load-balancer
routing. Every response must carry the expected **actual upstream address**;
a wrong or absent header fails the test. No diagnostic endpoint or process
identity is added to the production application.

## Test sequence and objective

1. Inspect both running containers and resource limits.
2. Authenticate via Nginx; credentials remain in memory and never enter URLs.
3. Receive an actual first snapshot from each process. Confirm both increment
   the same observed Redis key, then reset only that disposable fixture key.
4. Alternate 29 invalid upgrades between A and B, varying forged/duplicate
   forwarding headers; each must return HTTP 403 from the expected backend.
5. Accept authorized attempt 30 on B and receive a real snapshot.
6. Deny authorized attempt 31 on A and attempt 32 on B. Neither replica gets a
   new private allowance after the shared budget is exhausted.
7. Require one counter equal to 32, a positive TTL at most 60 seconds, and no
   changed secondary peer bucket. Remove only the observed test key.
8. Stop both APIs and the outbox writer before the standard restore drill;
   remove the disposable stack and its networks.

The handshake phase has a 40-second deadline. Requests are sequential, with no
load generator, emulator, cloud service or paid API. Docker startup/inspection
and the existing restore drill are separate phases outside that deadline.

## Reproduction

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_integration_tests.ps1 -DashboardMultiProcessAcceptance
```

Use a Compose version supporting `!override` (2.24.4+) and the project development
environment. `-UseExistingImages` is optional only when the existing application
image matches current backend source. The multiprocess profile cannot be combined
with the single-proxy/TLS or emulator profiles. Dependencies are inherited from
the base integration Compose service rather than copying credentials into files.

## Evidence and exclusions

On 2026-09-18, 22 targeted unit tests passed in 1.07 seconds (eight new cases plus
14 existing checks), alongside Ruff, strict mypy and PowerShell syntax validation.
Two integration tests passed in 43.47 seconds with the API CPU limits active.
Real Docker acceptance confirmed distinct processes and the resource bounds,
snapshots from both replicas, correct upstream selection for every attempt, and
the shared 30/31/32 boundary. This is not a timing or capacity comparison.

Restore passed with 87 tables and 283 rows in 81.765 seconds at migration
`0064_ai_evidence_projections`; both API writers were stopped first. Final Docker
queries found no owned containers or networks. Intermittent host CPU samples
were 19–71%, GPU 3–7%, with 15.2 GiB RAM free at preflight; these are not measured
peaks. Final samples were CPU 27% and GPU 3%.

The existing application image was reused: this increment changes acceptance
tooling and mounted proxy configuration, not backend source. The successful live
run used the two-replica profile; the single-proxy real deployment and TLS scenario
were not rerun in this increment. Their existing targeted unit checks passed.

Unit tests cover route
alternation, the unchanged single-proxy route, missing/wrong upstream evidence,
duplicate process identity and missing resource bounds.

The 16 active-stream slots remain **per process**, not a distributed simultaneous
connection cap. This increment does not test saturation, automatic balancing,
failover, process restarts, simultaneous races, Redis outage, TLS lifecycle or
production throughput. Same-host container replicas are not multi-host evidence.
The complete X-7 release gate remains open.
