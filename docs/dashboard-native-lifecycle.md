# X-7.8 — Native lifecycle prerequisite

The companion Android `DashboardLifecycle` implements a deterministic, single-owner
state machine with connection generations, stale evidence after 35 seconds, an
initial 30-second deadline and five bounded retries (30/60/120/120/120 seconds).
Authorization and protocol denials clear evidence; old callbacks cannot restore
it. Ten ordered snapshots followed by normal close complete without auto-restart.

Seven JVM tests use virtual time, avoiding network and emulator resource usage.
The payload is opaque: this is not JSON validation, a connected OkHttp client or
device acceptance. The future adapter must enforce envelope metadata, byte limits,
credential lifecycle, serialized callbacks, socket cancellation and timer cleanup.
HTTP 403 is terminal conservatively; native admission denial cannot reliably be
distinguished from permission denial before WebSocket upgrade.

No new dependencies or paid services. DOCX unchanged. Next is the transport/parser
adapter, then presentation and actual AAOS acceptance, before the deployment gate.

Companion validation: 44 JVM tests passed (seven new), lint zero errors and 15
warnings, and debug APK build successful in 56 seconds with one worker and a
1536 MiB JVM heap. No live-network/device validation was performed.
