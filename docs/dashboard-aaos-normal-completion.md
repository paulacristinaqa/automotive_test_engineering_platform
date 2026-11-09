# X-7.19 — Normal ten-snapshot AAOS completion

## Objective

Exercise the normal bounded server session on actual API 35, without injecting
network faults. Ten ordered snapshots on one WebSocket must end in COMPLETE,
retain the final preview as stale/not live, clear the credential input and
avoid automatic restart.

## Acceptance design

The existing loopback proxy forwards normally throughout. The host requires
exactly one accepted connection at initial LIVE, completion and after terminal
observation. This scenario alone selects a ten-minute integration JWT fixture;
other runs explicitly retain five minutes and production configuration is
unchanged. The host checks the returned lifetime is 600 seconds. LIVE must be
reported within 60 seconds of issuance, reserving ample time for nine remaining
30-second intervals. Clocks and refresh intervals are not changed.
The local 600-second budget isolates normal completion from local expiry.

The existing production client validates sequence numbers and enters COMPLETE
only on a normal close after ten snapshots. Instrumentation additionally checks
that the displayed final preview contains sequence 10, completion takes at least
269 seconds after Connect (also independently timed from host TCP acceptance),
the status says STALE / NOT LIVE, and the token
field is empty. It retains exactly the same preview and COMPLETE for 32 more
seconds, beyond the first reconnect backoff. The host rejects any new connection.

Three exact ordered checkpoints are required. The coordinator has a 360-second
bound; device completion has a 290-second wait after LIVE. Missing checkpoints
cannot pass. A delayed setup fails rather than relaxing authentication or
silently refreshing the JWT. No raw instrumentation output or credentials are
printed. The screenshot contains only the final cleared form and aggregates.

## Reproduction

Build Android sequentially with one Gradle worker as documented in
`dashboard-aaos-network-recovery.md`, then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardAaosNetworkAcceptance -DashboardAaosNormalCompletion -StartAaosEmulator -UseExistingImages
```

Only reuse images matching backend source. Completion cannot be combined with
expiry or exhaustion scenarios. The owned emulator uses one guest core, 2 GiB
RAM and software rendering. Compilation, device execution and restore checks
are sequential. No paid service is required.

## Evidence boundary

Four host cases cover successful ordering and omission of each checkpoint.
Existing JVM lifecycle/adapter tests verify normal close after ten frames,
retention of stale evidence, socket cancellation and no reconnect. Real-device
results must be recorded separately before this gate is marked passed.

This engineering-panel acceptance is not a whole-platform completion claim.
Accessibility, broader browser coverage, trusted-proxy deployment and arbitrary
network partitions remain distinct gaps. DOCX is unchanged.

## Earlier validation history (superseded by the successful run below)

The first attempt stopped before initial LIVE confirmation with an overly
narrow five-minute JWT setup budget. A scenario-specific ten-minute fixture
was introduced, retaining five minutes for all other runner modes. The second
attempt failed within the completion assertion phase; its precise failing
assertion was not retained. Review found a timing-origin issue: measuring from
UI recognition of LIVE can exclude already elapsed stream time. Instrumentation
now measures from Connect, with an independent host TCP-acceptance duration
check and more granular allowlisted failure phases. Device acceptance remains
pending until the corrected run passes.

The third attempt reached COMPLETE and passed duration/stale-status assertions,
but failed in `completion-preview` (node/text retrieval or sequence assertion).
Therefore final-preview retention, credential cleanup and the 32-second terminal
observation are NOT accepted yet. The failure phase is now split between preview
retrieval and sequence matching for the next diagnostic run; this final diagnostic
change has not been rebuilt or executed. No application behavior was changed.

Host validation: 57 tests, Ruff and mypy passed. Initial Android build/lint
passed in 37 seconds (59 JVM tests retained, zero lint errors/15 existing
warnings); the timing-diagnostic instrumentation rebuild passed in 19 seconds.
All three backend integration runs passed (24.33, 19.11 and 19.28 seconds).
No new restore report was produced for these failed AAOS runs; the existing
report belongs to X-7.18. Cleanup ran on all failures. CPU samples across these
attempts were 26–62%, GPU 10–19%, with 11.3 GiB free RAM in device-stage samples;
these are not measured peaks. No commit/PR/merge was performed.

## Successful acceptance — 2026-09-17

The preview node is now explicitly refreshed before reading its accessibility
text. Instrumentation also distinguishes node lookup, refresh/text retrieval
and sequence validation; failure screenshots are captured only after the
initial form phase and pulled locally without printing credentials or raw
output. The next actual-device run passed all assertions without changing
application runtime behavior. This is consistent with a stale accessibility
node contributing to the earlier failure, but the earlier combined diagnostics
do not establish its exact cause conclusively.

The host observed one TCP connection throughout, normal ten-snapshot completion
and no automatic restart. Android verified sequence 10, an empty token input,
COMPLETE / STALE / NOT LIVE, and an unchanged final preview for 32 seconds.
The inspected screenshot `dr-evidence/dashboard-aaos-network-completed.png`
visibly confirms the final state, empty credential field and sequence 10.
This targeted normal-completion gate is now passed.

Instrumentation build passed in 22 seconds. The retained Android JVM suite has
59 passing tests; this instrumentation-only change did not rerun JVM/lint tasks.
All 57 host tests passed again in 5.05 seconds; Ruff and strict mypy passed for
six files. Both integration tests passed in 20.28 seconds. Sampled CPU was
36–74%, GPU 5–16%; a device-stage sample had 10.3 GiB RAM free. These are
intermittent observations, not measured peaks or a capacity guarantee.

Restore passed with 87 tables/292 rows in 79.828 seconds at migration
`0064_ai_evidence_projections`. Owned integration containers and emulator were
confirmed absent after cleanup; final sampled CPU was 40%, GPU 5%. Both
repository diff checks passed. Changes remain local and uncommitted; no PR or
merge was performed. English Markdown is updated; DOCX remains unchanged.
