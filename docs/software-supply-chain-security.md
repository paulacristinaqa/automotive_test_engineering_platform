# Software supply-chain security

## Purpose

This baseline makes ATEP builds reviewable, repeatable, and independently evidenced. It protects
the development pipeline; it does not claim production certification or eliminate the need to
review findings.

Linux x86-64 with Python 3.14 is the canonical lock platform because it matches the container and
hosted CI runtime. The runtime uses the digest-pinned official Python 3.14.6 Alpine 3.24 image,
while integration CI continues to test the supported Python 3.12 minimum. The security workflow
retains its regenerated lock pair for seven days before
enforcing a byte-for-byte drift check. Windows developers install the committed Linux-compatible
graph; dependency updates are accepted only from the canonical workflow evidence.

## Enforced controls

| Surface | Control | Evidence |
|---|---|---|
| Python runtime | `requirements.lock` includes resolved runtime and build dependencies with SHA-256 hashes | lock drift test and `pip-audit` |
| Python development | `requirements-dev.lock` includes the complete quality/security toolchain with hashes | lock drift test and quality jobs |
| Container base | `Dockerfile` selects official Python 3.14.6/Alpine 3.24 by manifest digest and installs the runtime lock with `--require-hashes` | policy test and image build |
| Workflow dependencies | Every third-party action reference is a full 40-character commit SHA with a readable version comment | policy test |
| Repository history | Gitleaks scans the checked-out history without publishing PR comments or raw findings | security workflow result |
| Application source | CodeQL analyses Python with the `security-extended` query suite | GitHub code-scanning result |
| Python dependencies | `pip-audit` rejects known vulnerabilities and emits a CycloneDX JSON SBOM | job result and retained artifact |
| Container image | Syft emits a CycloneDX JSON SBOM and Grype rejects high or critical known vulnerabilities | job result and retained artifact |
| Release provenance | A protected main-only caller gates an input-free reusable builder that publishes one non-replaceable commit tag, signs SLSA provenance and the release CycloneDX SBOM with GitHub/Sigstore, and pushes both attestations to GHCR | release run, reusable-builder identity, GitHub attestations, OCI referrers, and 90-day release evidence |
| Promotion verification | The exact image digest must verify against this repository, the fixed reusable signer workflow, the supplied main commit/ref, and a GitHub-hosted signing runner before environment promotion | `gh attestation verify` gate and workflow-policy tests |
| Offline release evidence | The builder downloads the exact digest's attestation bundle and current roots, verifies the archived provenance, and emits a SHA-256/size manifest for the release report, SBOM, bundle, and roots | 90-day transfer package and future immutable archive copy |
| Sealed archive restore | A deterministic ZIP and separate receipt bind content, source/image identity, object key, manifest hash, size, and SHA-256; a fresh job downloads and restores them before release workflow success | seal/restore tests, cross-job download, and provider-neutral WORM contract |
| Revocation | Exact-digest withdrawal preserves evidence first, freezes promotion, removes attestations plus the affected package/referrers under dual review, and proves online verification/admission denial | incident record, archived package, API/package audit, and negative verification evidence |
| Updates | Dependabot proposes weekly grouped Python updates and weekly Actions/Docker updates | reviewed pull requests |

Workflow permissions are read-only by default. Only CodeQL receives `security-events: write`; the
protected approval job remains read-only, while its dependent reusable-builder call alone receives
package, OIDC, and attestation write permissions. Routine
SBOM artifacts are retained for 14 days, while release SBOM and aggregate release evidence are
retained for 90 days. None may contain application credentials.

## Local verification

Install the reviewed development graph and project without dependency re-resolution:

```powershell
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
```

Audit the runtime graph and run the policy tests:

```powershell
python -m pip_audit --require-hashes --disable-pip -r requirements.lock
python -m pytest -q tests/test_supply_chain_security.py
```

When `pyproject.toml` changes, regenerate both locks with the repository's pinned `pip-tools`
version and review every resolved change:

```powershell
pip-compile --all-build-deps --allow-unsafe --generate-hashes --no-emit-index-url --no-emit-trusted-host --output-file=requirements.lock --strip-extras pyproject.toml
pip-compile --all-build-deps --allow-unsafe --generate-hashes --no-emit-index-url --no-emit-trusted-host --output-file=requirements-dev.lock --strip-extras --extra=dev pyproject.toml
```

The development graph pins `pip` to 25.3 because the lock compiler's current integration uses
interfaces removed in pip 26.x. This compatibility pin belongs to the build toolchain, not the
runtime image, and should be removed after a verified `pip-tools` update supports the newer API.

## Finding and exception policy

1. Do not lower the scanner threshold or add an ignore rule merely to make CI pass.
2. Confirm the affected package or image layer and whether the vulnerable path is reachable.
3. Prefer an upstream fixed version or a newer digest-pinned base image, then regenerate evidence.
4. If no fix exists, record the advisory, impact, compensating control, owner, review date, and a
   time-bounded expiry before adding the narrowest possible exception.
5. Never include tokens, credentials, full environment dumps, or sensitive source excerpts in an
   exception or uploaded artifact.

## Active time-bounded exception

As of 5 August 2026, Grype reports the following findings against the CPython binary in the
official Python 3.14.6/Alpine 3.24 image. No stable fixed CPython release is available; the scanner
identifies only Python 3.15 pre-release or future versions as fixed. The exception is encoded in
`.grype.yaml` and cannot match another package name, version, package type, or advisory.

| Advisory | Exact component | Owner | Review and expiry | Compensating controls |
|---|---|---|---|---|
| CVE-2026-11940 | `python` 3.14.6, `binary` | ATEP maintainers | 5 September 2026 | Digest-pinned minimal official image, independent source/dependency analysis, weekly update review |
| CVE-2026-15308 | `python` 3.14.6, `binary` | ATEP maintainers | 5 September 2026 | Digest-pinned minimal official image, independent source/dependency analysis, weekly update review |
| CVE-2026-11972 | `python` 3.14.6, `binary` | ATEP maintainers | 5 September 2026 | Digest-pinned minimal official image, independent source/dependency analysis, weekly update review |

A stable Python release that fixes any advisory triggers immediate image update, exception removal,
SBOM regeneration, and retest. Any new high or critical finding remains blocking. Maintainers must
remove or formally re-review these entries no later than the stated date; expiry is not automatic
acceptance of continued risk.

## Remaining production work

- protect release environments with approvals and isolated credentials;
- retain release SBOMs alongside immutable artifacts for the required product lifetime;
- connect the portable archive to an immutable provider with retention locks, restore exercises, and revocation catalogue;
- move the reusable builder to a separately governed repository, pin callers to a reviewed SHA, and retain independent provenance evidence;
- integrate a managed secret service and define emergency credential rotation;
- define vulnerability-response ownership, service levels, and supplier escalation;
- assess automotive cybersecurity obligations and evidence against the intended deployment.
