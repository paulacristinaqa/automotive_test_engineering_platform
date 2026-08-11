# Kubernetes deployment baseline

This baseline deploys the ATEP control plane without committing credentials or assuming a
specific cloud provider. It is the first production-hardening slice, not a production approval.
PostgreSQL, Redis, RabbitMQ, ingress, TLS, durable shared object storage, and the secret manager
remain operator-owned services.

## Deployment model

The rollout is intentionally separated into four Kustomize targets:

1. `foundation` creates the `atep` namespace, non-sensitive configuration, identity boundaries,
   the initial artifact claim, and default-deny network policy;
2. `admission` installs the cluster-scoped image-integrity policy and binding without applying a
   namespace to those resources;
3. `migration` runs one bounded Alembic Job and must complete before application rollout;
4. `workloads` starts one API replica and one outbox worker after migration evidence is retained.

The API remains a singleton because it currently owns the test scheduler and module reconciler.
`Recreate` prevents two versions from owning those loops during rollout. This deliberately trades
rolling availability for correctness until leader election or separately deployed schedulers are
implemented.

## Required secret-manager contract

An approved secret manager or CSI/external-secret controller must materialize one namespaced
Opaque Secret named `atep-runtime-secrets`. The repository contains no Secret manifest and no
encoded placeholder values.

| Key | Required | Purpose |
|---|---|---|
| `ATEP_DATABASE_URL` | yes | PostgreSQL async SQLAlchemy URL, including managed credential reference/value |
| `ATEP_REDIS_URL` | yes | Redis URL used for rate limiting and live projections |
| `ATEP_RABBITMQ_URL` | yes | RabbitMQ URL used by readiness and the outbox worker |
| `ATEP_JWT_SECRET` | yes | random JWT signing material of at least 32 characters |
| `ATEP_BOOTSTRAP_ADMIN_EMAIL` | bootstrap only | initial administrator identity |
| `ATEP_BOOTSTRAP_ADMIN_PASSWORD` | bootstrap only | initial administrator credential, removed after first successful bootstrap |

Secret values must never be passed on the command line, stored in shell history, committed in an
overlay, or included in diagnostic output. Configure workload identity and the selected secret
provider so only the deployment controller can materialize the Secret. Application ServiceAccounts
have token automount disabled and receive no Kubernetes API RBAC permissions.

## Immutable image prerequisite

Both image transformers contain an all-zero digest and therefore fail closed. A release pipeline
must create a reviewed environment overlay that replaces it with the published ATEP image's real
`sha256` manifest digest in both the migration and workload targets. Mutable tags are not an
acceptable production input.

The initial repository promotion workflow validates this substitution and retains a separate
render plus evidence report for each ordered environment. It does not apply resources. Configure
the fixed GitHub environments and review procedure in
[`docs/release-promotion.md`](../../docs/release-promotion.md) before running it.

Before deployment, render and review every target:

```bash
kubectl kustomize deploy/kubernetes/foundation
kubectl kustomize deploy/kubernetes/admission
kubectl kustomize deploy/kubernetes/migration
kubectl kustomize deploy/kubernetes/workloads
```

Reject the release if the rendered output contains the zero digest, an unexpected registry, a
literal Secret, privileged execution, or an unapproved external endpoint.

## Cluster image admission gate

The separate `admission` target installs a native `ValidatingAdmissionPolicy` and binding for Kubernetes
1.30 or later. The binding selects only namespaces labelled `atep.dev/image-policy=enforced`; the
committed `atep` namespace carries that label. On every ATEP Deployment or Job create/update, the
policy denies application and init-container images unless they use the exact repository
`ghcr.io/paulacristinaqa/automotive_test_engineering_platform`, a lowercase SHA-256 manifest
digest, and a value other than the all-zero placeholder. Denials are also requested in the
Kubernetes audit trail.

This native admission policy enforces repository and digest identity inside the cluster. The
GitHub/Sigstore controller described below adds cryptographic provenance verification; both gates
are required. Promotion must still perform the independent verification described in
[`docs/release-provenance.md`](../../docs/release-provenance.md), and every gate must use the same
manifest digest.

Installing or changing the policy and binding requires cluster-level authorization. Apply
`foundation`, then `admission`, before migration; inspect the policy type-checking status, and do not remove the
namespace enforcement label to bypass a failed deployment. Clusters older than Kubernetes 1.30
are unsupported by this baseline and must fail before workload rollout.

## GitHub/Sigstore attestation admission

The namespace also carries `policy.sigstore.dev/include=true`. This label becomes active only
after the official Sigstore Policy Controller and GitHub trust policy are installed. The committed
[`github-attestation-policy-values.yaml`](admission/github-attestation-policy-values.yaml) accepts
no exemptions and restricts SLSA v1 provenance to:

- `ghcr.io/paulacristinaqa/automotive_test_engineering_platform` images;
- the `paulacristinaqa/automotive_test_engineering_platform` repository;
- `.github/workflows/reusable-release-builder.yml` on `refs/heads/main`; and
- the GitHub Actions OIDC issuer under the GitHub and Sigstore public trust authorities.

Use the exact chart versions reviewed in the official GitHub procedure. Verify and retain each
resolved OCI chart digest before installation; version tags alone are not immutable evidence.
The GitHub trust-policy chart is itself attested and must pass this verification:

```bash
gh attestation verify --owner github \
  oci://ghcr.io/github/artifact-attestations-helm-charts/trust-policies:v0.7.0

helm upgrade policy-controller --install --atomic \
  --create-namespace --namespace artifact-attestations \
  oci://ghcr.io/sigstore/helm-charts/policy-controller \
  --version 0.10.5

helm upgrade trust-policies --install --atomic \
  --namespace artifact-attestations \
  oci://ghcr.io/github/artifact-attestations-helm-charts/trust-policies \
  --version v0.7.0 \
  -f deploy/kubernetes/admission/github-attestation-policy-values.yaml
```

Do not install with `--set policy.organization` alone: that would trust every repository owned by
the account. Do not add `exemptImages`, broaden the image glob, remove the namespace label, or use
an unreviewed chart version to recover a failed rollout. Installation requires Kubernetes 1.27+
and Helm 3, while the native ATEP policy keeps the effective platform minimum at Kubernetes 1.30.

Before workload rollout, submit the approved attested digest and negative samples for an
unattested digest, another repository, another workflow, another source ref, and a malformed image.
Retain controller version/digests, `TrustRoot`, `ClusterImagePolicy`, policy status, admission
denials, and Kubernetes audit records. No live cluster installation is performed by this repository.

## Controlled rollout

After the approved image overlay and externally managed Secret exist:

```bash
kubectl apply -k deploy/kubernetes/foundation
kubectl apply -k deploy/kubernetes/admission
kubectl apply -k <approved-migration-overlay>
kubectl wait --for=condition=complete --timeout=180s job/atep-migrate -n atep
kubectl logs -n atep job/atep-migrate
kubectl apply -k <approved-workload-overlay>
kubectl rollout status deployment/atep-api -n atep --timeout=180s
kubectl rollout status deployment/atep-outbox-worker -n atep --timeout=180s
```

Use a unique migration Job name per release or remove only a previously completed Job after its
logs and status have been retained. Never delete a running migration to bypass a failed release.

The API Service is `ClusterIP`. An ingress controller namespace must carry the label
`atep.dev/api-access=true` before its pods can reach port 8000. A monitoring namespace must carry
`atep.dev/metrics-access=true`. Add TLS, authentication policy, approved hostnames, and rate-limit
calibration in an environment overlay; do not expose the Service directly as a `NodePort`.

## Workload identity overlay

The common ConfigMap keeps workload identity disabled. Enable it only in an environment overlay
after an approved mTLS proxy is deployed. Configure the environment's SPIFFE trust domain and the
proxy's exact direct-peer CIDRs; never use a broad network merely to restore connectivity. The
proxy must validate the client certificate, replace any caller-supplied XFCC with one validated
`URI=` field, and be the only network path to the ATEP pod. See
[`docs/workload-identity.md`](../../docs/workload-identity.md) for the contract, migration order,
negative tests, and pending live-evidence gate.

## Verification and rollback

Retain these items with the release evidence:

- rendered manifests and approved image digest;
- migration Job condition and non-sensitive logs;
- rollout status and pod events;
- `/health/live` and `/health/ready` results through the approved ingress path;
- SBOM, vulnerability result, signature, and provenance when those controls are available.

Roll back workloads by applying the previously approved digest overlay. Database rollback is never
automatic: migrations must remain backward compatible, and any downgrade requires a separately
reviewed recovery procedure and verified backup. The initial `ReadWriteOnce` artifact claim is not
shared multi-replica object storage and must be replaced before horizontal API scaling.
