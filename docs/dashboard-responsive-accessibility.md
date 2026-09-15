# X-7.6 — Responsive presentation and accessibility checks

## Changes

The engineering shell now provides a keyboard-visible skip link to a focusable main landmark.
Status messages have explicit atomic live-region semantics and the password input references its
credential-handling note. CSS permits long text to wrap, removes intrinsic minimum widths from
form controls and lets the snapshot heading/freshness row wrap on narrow screens.
No authentication policy, transport protocol, dependency or paid service changed.

## Automated acceptance

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\run_integration_tests.ps1 -DashboardPresentationAcceptance
```

The optional Windows runner uses the real installed API, disposable credentials and isolated
Chrome with GPU acceleration disabled. It retains login/logout and no-role rejection checks.
This presentation switch does not repeat the five-minute lifecycle test unless explicitly combined
with `-DashboardLifecycleAcceptance`.

| Check | Objective |
|---|---|
| Skip link | Tab reveals the link; Enter focuses main; the next Tab reaches email. |
| Native validation | Invalid email remains invalid and receives focus without entering the signed-in view. |
| 320, 768, 1280 CSS-pixel widths | Login and live operations states have no page-level horizontal overflow. |
| Control geometry | Visible inputs, selector and buttons stay within viewport horizontal bounds and are at least 44 CSS pixels high at normal text size. |
| Enlarged text | At 320 pixels, setting the root text size to 200% produces a computed size of at least 32 pixels without page-level horizontal overflow. |
| Logout focus | Logout returns focus to email; a subsequent keyboard login still receives data. |
| Markup regression | Python tests protect skip-link target, labels, atomic status regions and the credential-note relationship. |

Text enlargement is a browser-injected CSS test, not OS scaling or browser zoom. The script restores
the original text size and viewport. JSON remains a focusable internal scrolling region rather than
forcing the whole page to scroll horizontally. Screenshots contain only disposable aggregate data;
no password or token values are captured or saved as browser state.

## Evidence

On 2026-09-15, all listed browser checks passed. Eight full-page screenshots (login/live at three
widths plus enlarged text) were visually inspected through the browser verification skills.
Local evidence is under ignored `dr-evidence/dashboard-x76-*.png`. The regular Docker integration
suite passed both tests in 19.71 seconds. Focused Python asset tests, Ruff and mypy passed.
The full local regression passed 597 Python tests and 28 Node tests. PostgreSQL restore passed;
the temporary stack was removed and Chrome was closed. CI runs standard automated gates, while
the Windows presentation runner remains optional local acceptance evidence.

During initialization a whole-host sample showed CPU 67% and GPU 7%; during browser work CPU 24%
and GPU 6%. In the latter sample RabbitMQ used 316.28% container CPU, while API memory was 152.7 MiB.
Container CPU uses a different scale from total-host CPU. These are samples, not peak measurements
or attribution of all host usage to the test. No emulator or GPU computation workload was started.

## Limitations and next gate

These are targeted checks, not an accessibility certification. Visual inspection showed word
breaks at 200%/320 pixels, and the native selector can abbreviate its displayed option at that size.
Opening the selector is still necessary to see its complete option labels; this remains a usability
limitation. The engineering JSON panel has internal horizontal scrolling and is not a mobile-first
KPI presentation. Browser-native validation messages follow the browser locale.

Screen-reader announcements, contrast auditing, high-contrast/forced-colors mode, browser zoom,
OS scaling, physical touch devices and non-Chromium browsers are not established by these results.
AAOS and trusted-proxy deployment acceptance remain the next cross-platform gates; prerequisites
must be checked before starting an emulator or changing the Android repository.
Markdown is the current workbook source; DOCX snapshots are unchanged.
