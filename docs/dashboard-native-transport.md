# X-7.9 — Native transport adapter

The companion `DashboardNativeClient` now wires the native request and lifecycle
to OkHttp, with serialized callbacks, monotonic polling, socket cancellation,
caller-provided token lifetime and conservative local expiry. Native requests
contain Authorization and no Origin. The adapter sends no application messages.

The envelope parser checks bounded UTF-8 size/nesting, frame and export versions,
sequence shape, requested view, retention label and query-time freshness metadata.
Raw envelopes retain observation timestamps. Per-view aggregate schemas are not
fully validated, and the post-receipt byte check is not a transport allocation cap.

Nine new companion JVM tests use JSON and an injected WebSocket factory. They do
not establish a real server handshake, Android UI or AAOS acceptance. Android JSON
platform behavior must still be checked on-device; the JVM implementation is a
test-only dependency, not a production dependency or paid service.

Next: Android presentation/session ownership, then actual backend and AAOS
acceptance. No ATEP runtime changes; DOCX remains unchanged.

Local companion evidence: 53 JVM tests passed, including nine new adapter/parser
tests; lint and debug APK build passed in 52 seconds with one worker and a 1536 MiB
heap. Initial JUnit signature failure was fixed before this successful run.
After lint review, fixed-delay polling replaced fixed-rate scheduling and the
test-only JSON library was updated. Final production build/lint passed in 1m 4s,
with zero errors and 15 existing warnings. Boundary tests were strengthened and
rerun separately without another production change.
