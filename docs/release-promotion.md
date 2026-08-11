# Release promotion evidence

This initial CI/CD promotion slice validates one declared source commit and immutable container
digest through `development`, `staging`, and `production` in that order. It creates GitHub
deployment records and retains reviewed Kubernetes renders, but it deliberately does not apply
resources to a cluster. Cluster credentials, provider identity, ingress, TLS, managed secrets,
smoke tests, and rollback execution remain separate production gates.

## Security boundary

The workflow accepts only:

- a fixed environment choice;
- a non-zero lowercase `sha256` image manifest digest; and
- a full lowercase 40-character source commit SHA already contained in `main`.

The evidence builder renders the committed foundation, migration, and workload Kustomize targets.
It substitutes only the exact reviewed all-zero application image placeholder, requires every
rendered application image to use the same repository and digest, rejects literal Kubernetes
Secrets, and fails if any zero digest remains. The resulting JSON binds the declared environment,
source SHA, image digest, full image reference, timestamps, resource counts, and SHA-256 of every
rendered manifest.

This evidence proves that a declared commit can produce policy-conforming manifests for a declared
digest. It does **not** yet prove that the digest was built from that commit. Signing, build
provenance, and verification before promotion remain required hardening.

## Required GitHub environment configuration

Create the three repository environments with these exact names before dispatching the workflow:

| Environment | Required configuration | Retained evidence |
|---|---|---|
| `development` | restrict deployment branches/tags to the approved release policy; set environment variable `ATEP_PROMOTION_ENABLED=true` only after review | 30 days |
| `staging` | use the same branch restriction; require the development job to succeed; set `ATEP_PROMOTION_ENABLED=true` only after review | 60 days |
| `production` | restrict releases to the approved policy; configure required reviewers, prevent self-review, disallow administrator bypass where supported, and set `ATEP_PROMOTION_ENABLED=true` only after review | 90 days |

The enablement variable is a second fail-closed control. A missing or differently cased value makes
the environment job fail even if GitHub created an unprotected environment automatically. It does
not replace GitHub required reviewers or branch/tag policies.

Environment protection is repository configuration and cannot be asserted by workflow YAML alone.
The repository owner must inspect the environment settings and retain a settings review before the
first production exercise. GitHub documents that protection rules are evaluated before a job is
sent to a runner and that required-reviewer approval can be configured to prevent self-approval.

## Running a validation

1. Confirm the source commit is merged into `main` and all required CI checks passed.
2. Obtain the published image **manifest digest**, not a mutable tag or a local image ID.
3. Open **Actions**, select **promotion-evidence**, and choose **Run workflow**.
4. Enter the full source SHA, image digest, and highest target environment.
5. Review each lower-environment artifact before approving the next protected environment.
6. For production, a reviewer other than the initiator should inspect the evidence and approve or
   reject the pending deployment in GitHub.

Selecting `staging` always passes through `development`; selecting `production` always passes
through both lower environments. Per-environment concurrency prevents two validations from using
the same environment simultaneously.

## Evidence contract

Each environment artifact contains:

- `foundation.yaml`;
- `migration.yaml`;
- `workloads.yaml`; and
- `promotion-evidence.json` using schema version `1.0.0`.

The manifests contain no runtime Secret values. Review the evidence JSON and recompute the three
manifest hashes before using it as an input to a future deployment controller. Do not place cluster
credentials, bootstrap credentials, external-secret values, or private endpoints in an artifact.

## Next deployment increment

The next stage may perform a real development deployment only after approved workload identity and
secret-provider bindings exist. That stage must verify image signature and provenance, run the
migration once, retain its terminal condition and non-sensitive logs, apply workloads, run bounded
readiness/authentication/RBAC/outbox smoke tests, and retain rollback evidence. Staging and
production must reuse the same verified digest; production database rollback must never be
automatic.

## References

- [GitHub deployment environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments)
- [GitHub deployment protection rules](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [GitHub deployment review procedure](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments)
