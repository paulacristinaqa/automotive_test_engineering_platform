# Signed image provenance

The ATEP release boundary publishes one commit-addressed container image to GitHub Container
Registry (GHCR), generates signed SLSA build provenance and a signed CycloneDX SBOM attestation,
and records a non-sensitive release summary. Promotion verifies the provenance before any GitHub
environment gate is entered.

This is an initial reusable-builder trust boundary. The protected caller performs only approval
and source checks; an input-free reusable workflow builds, publishes, and signs. The builder is
still governed in the same repository and therefore does not by itself prove independent SLSA
Build Level 3 isolation, deploy the image, or replace admission control in a real Kubernetes cluster.

## Release invariants

- The workflow runs manually from `refs/heads/main` and requires the exact GitHub environment
  variable `ATEP_RELEASE_ENABLED=true`.
- The checked-out commit must equal `github.sha` and be contained in `origin/main`.
- The image name is fixed as
  `ghcr.io/paulacristinaqa/automotive_test_engineering_platform`.
- The only published tag is `sha-<40-character commit SHA>`; `latest` and version-floating tags are
  not produced.
- An existing commit tag causes failure instead of replacement.
- The image receives OCI source, revision, and title labels.
- The build action records the registry manifest digest; downstream evidence never trusts a tag as
  the immutable identity.
- The approval job has read-only contents access. Only its dependent reusable-builder call receives
  `packages: write`, `id-token: write`, and `attestations: write`.
- The reusable workflow declares no caller-controlled inputs or secrets and verifies its exact
  `job.workflow_ref` identity on `refs/heads/main` before authenticating to the registry.
  Repository contents remain read-only.
- Registry authentication uses the short-lived job `GITHUB_TOKEN`; it is removed in an `always()`
  cleanup step.

## Signed attestations

The pinned first-party `actions/attest` action creates two Sigstore-signed attestations for the
same image name and digest:

1. SLSA build provenance, binding the subject to the repository, workflow identity, source ref,
   source commit, triggering event, and hosted runner context;
2. a CycloneDX SBOM predicate generated from the published digest.

Both bundles are pushed as OCI referrers and associated with the repository's GitHub attestation
records. The action's optional organization-only storage record is disabled because this project
is owned by a personal account. The workflow also retains `release-evidence.json` and the release
SBOM for 90 days.

The signed statement proves a claim made by the reusable builder. It does not make the workflow
itself trustworthy: branch protection, code review, pinned actions, least privilege, isolated
release configuration, and future independent builder governance remain necessary controls.

## Promotion verification

Before `development`, the promotion workflow authenticates to GHCR and runs `gh attestation
verify` against the exact `oci://<image>@<digest>` subject. Verification requires:

- this exact repository as the attestation owner;
- `.github/workflows/reusable-release-builder.yml` as the signer workflow;
- the supplied source commit as the provenance source digest;
- `refs/heads/main` as the source ref;
- the standard SLSA provenance predicate; and
- a GitHub-hosted rather than self-hosted signing runner.

Missing, invalid, mismatched, or externally signed provenance stops the promotion before any
environment job. The existing Kustomize evidence then binds the already verified digest to each
ordered environment.

## Required repository configuration

Create a GitHub environment named `release` and configure:

1. deployment branch/tag policy allowing only `main`;
2. required review according to the project's separation-of-duties policy;
3. self-review prevention and administrator-bypass denial where supported;
4. environment variable `ATEP_RELEASE_ENABLED=true` only after the settings review; and
5. no long-lived registry, signing, or cloud credential.

Confirm that Actions has package write permission for the repository and that a pre-existing GHCR
package with the same name is linked to this repository. The initial package may be private by
default; choose visibility intentionally before expecting anonymous verification or pulls.

## First live evidence procedure

1. Merge this workflow through normal review and wait for all CI/security checks.
2. Configure and independently review the `release` environment.
3. Run `release-image` from the `main` branch once.
4. Confirm the immutable commit tag and manifest digest in GHCR.
5. Download and inspect the retained release report and CycloneDX SBOM.
6. Verify the OCI subject independently with the documented `gh attestation verify` policy.
7. Run the promotion workflow with the same source SHA and digest, targeting `development` only.
8. Retain the release run, attestation URLs, verification output, and promotion artifact as the
   first live evidence set.

The signer check deliberately names the reusable workflow, not the manual caller. GitHub records
the workflow containing `actions/attest` as the attestation signer. A future move to a separately
governed builder repository must update the signer repository, workflow, admission subject, and
verification tests atomically.

## Portable archive and revocation

After creating both attestations, the builder downloads the digest's GitHub attestation JSONL,
captures current trusted roots, and verifies the SLSA statement again using only that bundle and
root file while retaining the exact online signer/source policy. It then creates
`release-archive-manifest.json`, which binds the release report, CycloneDX SBOM, attestation bundle,
and trusted roots by role, filename, SHA-256, and byte size. The portable package is retained for
90 days for transfer to approved immutable long-term storage.

Withdrawal is deliberately separate from archive creation. An archived signature can remain
cryptographically valid after an artifact is no longer authorized, so consumers must also consult
current online verification, admission, and revocation state. Follow
[`release-evidence-lifecycle.md`](release-evidence-lifecycle.md) before deleting an attestation or
GHCR image/referrer.

No release workflow is dispatched automatically by this increment. Publishing the first package
is an explicit operator action because it creates an externally consumable artifact.

## Remaining hardening

- move the reusable builder into a separately governed repository and pin callers to a reviewed SHA;
- generate a multi-architecture manifest when required by deployment targets;
- install the reviewed GitHub/Sigstore admission charts by retained OCI digest and execute the
  committed exact-workflow policy against positive and negative images;
- bind the portable package to approved immutable product-lifetime storage and exercise restore;
- connect the revocation runbook to an external catalogue and execute a disposable live exercise;
- add release versioning without mutable tags and an emergency release procedure; and
- calibrate the control set against the intended ISO/SAE 21434 and supplier evidence obligations.

## References

- [GitHub artifact attestation guide](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub reusable-workflow attestation guidance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/increase-security-rating)
- [GitHub reusable workflow reference](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations)
- [GitHub CLI attestation verification](https://cli.github.com/manual/gh_attestation_verify)
- [GitHub Container Registry guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub Kubernetes attestation enforcement](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/enforce-artifact-attestations)
