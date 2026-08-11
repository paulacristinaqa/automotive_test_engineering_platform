# Signed image provenance

The ATEP release boundary publishes one commit-addressed container image to GitHub Container
Registry (GHCR), generates signed SLSA build provenance and a signed CycloneDX SBOM attestation,
and records a non-sensitive release summary. Promotion verifies the provenance before any GitHub
environment gate is entered.

This is an initial hosted-build trust boundary. It does not yet deploy the image, establish SLSA
Build Level 3, provide an independent reusable trusted builder, or replace admission control in a
real Kubernetes cluster.

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
- The release job alone receives `packages: write`, `id-token: write`, and `attestations: write`.
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

The signed statement proves a claim made by the release workflow. It does not make the workflow
itself trustworthy: branch protection, code review, pinned actions, least privilege, isolated
release configuration, and future reusable trusted-builder separation remain necessary controls.

## Promotion verification

Before `development`, the promotion workflow authenticates to GHCR and runs `gh attestation
verify` against the exact `oci://<image>@<digest>` subject. Verification requires:

- this exact repository as the attestation owner;
- `.github/workflows/release.yml` as the signer workflow;
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

No release workflow is dispatched automatically by this increment. Publishing the first package
is an explicit operator action because it creates an externally consumable artifact.

## Remaining hardening

- move build and signing into a reviewed reusable workflow with restricted inputs;
- generate a multi-architecture manifest when required by deployment targets;
- install the reviewed GitHub/Sigstore admission charts by retained OCI digest and execute the
  committed exact-workflow policy against positive and negative images;
- define long-term SBOM, attestation, package, and vulnerability-evidence retention;
- add revocation/deletion coordination for compromised images and attestations;
- add release versioning without mutable tags and an emergency release procedure; and
- calibrate the control set against the intended ISO/SAE 21434 and supplier evidence obligations.

## References

- [GitHub artifact attestation guide](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub CLI attestation verification](https://cli.github.com/manual/gh_attestation_verify)
- [GitHub Container Registry guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [GitHub Kubernetes attestation enforcement](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/enforce-artifact-attestations)
