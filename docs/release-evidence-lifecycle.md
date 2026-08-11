# Release evidence lifecycle and revocation

This runbook defines how ATEP preserves portable release evidence and withdraws trust from a
compromised or obsolete image. It supplements online GitHub/Sigstore verification; an archived
bundle is historical evidence and is never, by itself, proof that an image remains authorized.

## Portable release archive

Every successful reusable-builder run first assembles one offline-verification package containing:

- `release-evidence.json`, binding source SHA/ref, immutable image digest, and attestation URLs;
- `atep-release-image.cdx.json`, the CycloneDX SBOM generated from the published digest;
- the GitHub attestation JSONL bundle downloaded for that exact OCI digest;
- `trusted_root.jsonl`, refreshed during the same run; and
- `release-archive-manifest.json`, binding the four files by role, name, byte size, and SHA-256.

The builder verifies the downloaded SLSA provenance with the archived bundle and trusted root,
then seals those files and the manifest into deterministic `atep-release-evidence.zip`. A separate
`release-archive-receipt.json` binds its SHA-256, size, entry count, source/image identity, manifest
hash, and content-addressed provider object key. A fresh job downloads these two transfer files and
restores them into an empty directory before the workflow can succeed.

Verification keeps the same repository, reusable signer workflow, source SHA/ref, and hosted-runner
constraints used by promotion. The archive contains no registry token, environment value, image
layer, application secret, deployment credential, or provider credential.

GitHub Actions retention remains 90 days. Before expiry, an approved evidence exporter must copy
the sealed ZIP and receipt to immutable, access-logged storage under the product evidence retention
schedule and satisfy [`release-archive-provider-contract.md`](release-archive-provider-contract.md).
The repository does not pretend that the workflow artifact or local restore smoke test is
product-lifetime automotive retention.

After a provider adapter uploads and reads back the object, `tools/validate_archive_export.py`
normalizes its non-sensitive evidence. The gate re-restores the local seal, compares the exact key,
version, SHA-256, size, locked-retention deadline, encryption mode, writer identity, audit event,
and timestamps, then emits a non-replacing `release-archive-export-receipt.json`. Provider policy
provisioning and the adapter's live API evidence remain external deployment responsibilities.

The initial AWS adapter performs the pre-upload restore, atomic conditional S3 write, explicit
`COMPLIANCE` retention, exact KMS binding, versioned metadata verification, and complete streamed
read-back. It requires an STS assumed-role identity in the expected archive account and does not
accept long-lived IAM-user identity. The adapter is not enabled by a release workflow until the
AWS foundation and destructive negative acceptance exercise are independently approved.

## Offline verification

On a clean verification host, first compare every archived file with
`release-archive-manifest.json`. Then verify the OCI digest with the archived bundle and trusted
root while enforcing the exact signer policy:

```bash
gh attestation verify \
  "oci://ghcr.io/paulacristinaqa/automotive_test_engineering_platform@sha256:<digest>" \
  --repo paulacristinaqa/automotive_test_engineering_platform \
  --bundle "sha256:<digest>.jsonl" \
  --custom-trusted-root trusted_root.jsonl \
  --signer-workflow paulacristinaqa/automotive_test_engineering_platform/.github/workflows/reusable-release-builder.yml \
  --source-digest <40-character-source-sha> \
  --source-ref refs/heads/main \
  --deny-self-hosted-runners
```

Regenerate trusted roots whenever new signed material enters an offline environment. A previously
archived root does not tell an isolated verifier about a later key revocation, so offline results
must be evaluated together with the current revocation register and incident record.
On Windows, GitHub CLI writes the bundle as `sha256-<digest>.jsonl` because colons are not valid in
ordinary filenames; use that generated name without changing the manifest.

## Revocation triggers

Start the procedure when any of these conditions is confirmed or reasonably suspected:

- source, dependency, builder, signing identity, or runner compromise;
- materially incorrect provenance or SBOM;
- release produced outside the approved main/review path;
- exploitable defect requiring immediate withdrawal; or
- image or attestation deletion that breaks the evidence chain.

## Fail-closed revocation procedure

1. Declare an incident owner, affected digest, source SHA, discovery time, reason, and scope.
2. Freeze release and promotion enablement; stop pending rollouts without deleting evidence.
3. Download and independently hash the current attestation bundle, trusted roots, SBOM, release
   report, workflow logs, and package metadata before destructive actions.
4. Confirm a known-good replacement or rollback digest and its independent provenance.
5. Remove the affected GitHub attestations by exact subject digest through the personal-account
   attestation lifecycle API, using a separately approved credential with attestation write scope.
6. Remove or quarantine the exact GHCR package version and OCI referrers; never delete by a broad
   tag or repository pattern. Confirm that online verification now fails for the withdrawn digest.
7. Verify that GitHub/Sigstore admission rejects a new workload using the digest, and replace any
   running workload through the normal reviewed promotion path.
8. Notify consumers and record affected environments, vehicles/test assets, compensating controls,
   decision approvals, timestamps, and verification evidence.
9. Preserve the historical offline archive and incident record under legal/evidence retention;
   mark them revoked in the external evidence catalogue rather than rewriting signed history.
10. Re-enable release or promotion only after independent review confirms containment, replacement
    provenance, negative verification/admission evidence, and monitoring coverage.

Deletion is intentionally not automated by this repository. It changes external trust state and
package availability and therefore requires incident authority, exact digest confirmation, a
preserved evidence copy, and a second-person review.

## Required exercises

- Archive integrity: alter one byte in each file and confirm the manifest comparison fails.
- Offline positive: verify the exact digest, signer, source SHA/ref, and hosted runner successfully.
- Offline negative: change the signer, source SHA/ref, bundle, trusted root, or digest and confirm
  verification fails closed.
- Revocation: withdraw a disposable test digest and demonstrate failure in online verification,
  promotion, and Kubernetes admission without affecting another digest.
- Restore: recover the archive from the long-term store and repeat verification on a clean host.

## References

- [GitHub attestation lifecycle](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/manage-attestations)
- [GitHub offline attestation verification](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline)
- [GitHub CLI attestation download](https://cli.github.com/manual/gh_attestation_download)
- [GitHub personal-account attestation API](https://docs.github.com/en/rest/users/attestations)
