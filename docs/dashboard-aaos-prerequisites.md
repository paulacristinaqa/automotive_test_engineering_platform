# X-7.7 — AAOS prerequisites and native request foundation

The CarSystemUI showcase PRs 1–4 are consolidated in main at
`a76da4f32f06928a509ba50ca1112b3f79b43f45`. Their review corrected simulator
motion prerequisites and live test-run disposal/authorization handling; 32 unit
tests passed, with zero lint errors and 15 warnings. This was not device testing.

The next prerequisite is `DashboardNativeContract` in the companion repository:
an allowlisted native upgrade request with header authentication and no Origin.
HTTPS is required except explicit local-development HTTP opt-in for loopback or
10.0.2.2. URL credentials, non-root paths, query strings and fragments are rejected.
Tokens are bounded to 4096 printable non-space ASCII characters and are never
placed in URLs. The returned request contains credentials and must not be logged.

This is a request builder, not a running client. Its constants record the backend
30-second refresh and ten-snapshot limits without enforcing a lifecycle yet.
Five companion JVM tests cover routes/headers, transport policy, URL rejection,
token validation and constants. No Python runtime behavior changes in this slice.

Local companion verification: 37 unit tests passed (five new), lint analysis and
debug APK build passed in 54 seconds, with zero lint errors and 15 warnings.
Tests used one Gradle worker and a 1536 MiB heap; no emulator was started.

## Remaining ordered gates

1. Implement/test native socket lifecycle, bounded reconnect, stale indicators,
   denied-session cleanup, normal completion and credential lifecycle.
2. Wire the Android presentation and obtain device-side evidence. An installed
   SDK/AVD alone is not proof of readiness; check device connection before running.
3. Verify real AAOS scenarios from `dashboard-acceptance.md`, retaining versions,
   results and redacted evidence. Do not treat simulator defaults as VHAL observations.
4. Proceed to trusted-proxy deployment acceptance after the Android gate.

No emulator or paid infrastructure is required for this prerequisite. Complete
AAOS acceptance, AOSP image builds, screen-reader/contrast and proxy deployment
remain pending. Markdown is current; DOCX is unchanged.
