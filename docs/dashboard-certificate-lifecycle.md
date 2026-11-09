# X-7.23 — Local certificate expiry and replacement

Status: implemented; live Docker acceptance pending.

## Contract

DASH-NF-070 requires an explicitly trusted but expired certificate to fail with
OpenSSL verification code 10 (certificate expired). A replacement certificate
must differ from the original, be actually served by Nginx, reject the old
explicit trust configuration, and recover verified HTTPS login and WSS snapshots
after the client explicitly selects the replacement trust certificate.

## Implementation

The existing X-7.21 TLS runner first validates the original certificate. The
optional lifecycle phase then creates an expired certificate with validity from
two days ago to yesterday, using OpenSSL `x509 -not_before/-not_after`. System
time is never changed. Both expired and replacement material stay under the
same temporary directory used by the disposable TLS fixture.

Nginx is recreated with the expired certificate mount. A verified TLS handshake
must fail specifically with code 10, not merely a trust, hostname or TCP error.
Nginx is then recreated with a newly generated certificate/key pair. The served
DER certificate fingerprint must match the replacement file. The original
client trust must reject it; the new explicit trust must pass the existing TLS
1.2/1.3, hostname, HTTPS login and WSS first-snapshot checks.

This is intentional **restart-based replacement**, not seamless reload, automatic
renewal or preservation of an existing WebSocket. No trust store, cloud account,
public CA, paid API, browser setting or real vehicle is involved. The certificates
are local self-signed test material, not a production issuance chain.

## Reproduction

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_integration_tests.ps1 -DashboardCertificateLifecycleAcceptance
```

This enables the existing TLS profile, which removes API host port publishing
during TLS acceptance. It must not be combined with the multiprocess or emulator
profile. Use `-UseExistingImages` only when the existing application image matches
backend source. OpenSSL must support `x509 -not_before/-not_after`; the local
Git for Windows OpenSSL 3.5.6 supports both. No new package was installed.

The runner stops the proxy before removing temporary certificates, then stops
application writers and performs the existing PostgreSQL restore drill. Outer
cleanup removes owned containers and networks, including on failure.

## Test objectives and current evidence

- Actual certificate generation: expired notAfter is in the past; original,
  expired and replacement certificate fingerprints differ; temporary files are
  removed by the unit fixture.
- Negative oracle: code 10 is accepted as expiry evidence; codes 18 and 62,
  successful TLS negotiation and connection refusal cannot pass that assertion.
- Existing TLS/proxy/multiprocess admission tests: regression protection for
  trust settings, routing evidence and shared admission helpers.

On 2026-10-26, 28 targeted tests passed in 3.01 seconds, including six new
lifecycle cases. Strict mypy passed for the three changed/new Python files.
Docker Desktop was not running at preflight. **No real Nginx expiry, replacement,
HTTPS/WSS recovery or restore pass is claimed for X-7.23 yet.**

Remaining exclusions include CA-chain renewal, revocation, seamless reload,
expiry during an already established stream, Android/browser trust and combined
TLS/multiprocess deployment acceptance. The full X-7 release gate remains open.
