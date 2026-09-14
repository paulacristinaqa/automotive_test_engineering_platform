# X-7.1 — Real Chromium protocol acceptance

## Recorded execution

At 2026-09-14 08:09:23 UTC, real headless Chrome on Windows passed five sequential checks against
the disposable Linux-container API. The fixture was opened, visually inspected and operated with
agent-browser 0.37.1 and bundled Node 24.19.0. The browser reported HeadlessChrome/152.0.0.0,
Windows NT 10.0, Win64 (UA version, not an unreduced build number).

| Scenario | Objective | Result |
|---|---|---|
| Browser snapshot | Verify authenticated version, view, sequence and freshness in a real WebSocket client | Passed |
| Invalid token | No snapshot before close 4401 | Passed |
| Authentication timeout | No token: close 4401 without data | Passed |
| Read-only stream | Snapshot followed by attempted command: close 1008 | Passed |
| Native Origin denial | Browser attempt on the native route: failed upgrade/1006 | Passed |

The native denial is an expected browser network rejection; 1006 alone is not a diagnostic for
Origin policy. The separate protocol integration establishes the corresponding HTTP 403.
Visual checks confirmed content, the start control and the five-pass result. This is a test
fixture, not a product dashboard, and its server obtains a disposable administrator token:
end-user browser login is NOT validated by this result.

## Reproduction and safety

Run `tools/run_integration_tests.ps1 -DashboardBrowserAcceptance` from the repository root.
After normal integration, open `http://localhost:8080` and click **Run five sequential checks**.
The fixture has a 180-second deadline and binds to loopback only. Token/result requests require
the exact fixture Origin and Host. Never deploy or expose this test-only token issuer.
The default integration command and CI do not run this optional browser step.

The ignored `dr-evidence/dashboard-browser-acceptance.json` stores only timestamp, case statuses,
fixture identity and user agent. A new run removes the old report before starting, preventing a
timeout from appearing as a fresh pass. Screenshots `dashboard-browser-before.png` and
`dashboard-browser-after.png` in the same folder contain no tokens or snapshot payloads.
Local evidence remains until manually removed; this document preserves the reviewed result.
The runner closes the fixture after result submission or timeout and cleans up Docker services.

Chrome used an isolated session with `--disable-gpu`, closed after capture. No personal profile
or emulator was used. Host samples: CPU 17%/GPU 14% during preparation and CPU 37%/GPU 13% during
browser execution; API memory was 152.6 MiB in the latter sample. These are not peaks and include
other applications. No paid services were introduced.

## Remaining gates

- Actual user login and product dashboard UI, including expiry and permission-loss handling.
- Reconnect/backoff, stale-state display and full bounded-session acceptance in the real client.
- AAOS: the local CarSystemUI repository exists, but `adb devices -l` found no connected device.
  No Android build, emulator or repository change was performed.
- TLS/reverse-proxy deployment and agreed resource/capacity acceptance.

The browser skills guided real-engine navigation, visual inspection and session cleanup.
X-7 and Volume X remain in progress.
