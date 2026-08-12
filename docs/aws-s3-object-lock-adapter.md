# AWS S3 Object Lock archive adapter

This document defines the first concrete provider adapter for the ATEP immutable release archive.
The repository implements and tests the adapter plus a Terraform foundation, but does not
provision an AWS account or execute a live plan/apply, upload, denial, or restore exercise.

## Safety boundary

The adapter accepts only the deterministic sealed ZIP and local receipt. It:

1. validates and fully restores the local archive before any network write;
2. requires a canonical general-purpose S3 bucket, exact 12-digit owner, and exact KMS key ARN;
3. confirms through STS that the writer is an assumed role in the archive account;
4. searches the deterministic key's version history and rejects versions or delete markers;
5. issues `PutObject` with `If-None-Match: *` as the atomic non-replacement control;
6. sends the full-object SHA-256 and requires `COMPLIANCE` retention until the approved date;
7. requires SSE-KMS with the exact customer-managed key and an S3 Bucket Key;
8. captures the immutable `VersionId` returned by S3;
9. reads metadata and the complete object back by that exact version with checksum mode enabled;
10. compares object mode, retention, version, type, size, encryption, SDK checksum, and streamed
    SHA-256 with the local receipt; and
11. emits `provider-upload-evidence.json` and the normalized
    `release-archive-export-receipt.json` only after every check succeeds.

The adapter never requests delete, lifecycle, bucket-policy, Object Lock configuration,
governance-bypass, legal-hold administration, KMS administration, or CloudTrail administration.

## Required AWS foundation

The declarative foundation in `deploy/terraform/aws-archive-foundation/` now defines the archive
bucket, archive KMS key, writer/restore roles, bucket policy, and CloudTrail. Before live use, an
independently reviewed archive account and external control owners must still provide:

- an approved account and globally unique archive bucket name for the planned versioned Object
  Lock bucket;
- a bucket policy that denies insecure transport, non-KMS writes, the wrong KMS key, retention
  modes other than `COMPLIANCE`, and retention shorter than the approved schedule;
- existing KMS administrator roles separate from archive writers;
- independently governed CloudTrail destination storage and encryption with the required delivery
  policies;
- an account-wide GitHub OIDC provider and the exact current writer/restore subject claims;
- encrypted, locked remote Terraform state outside the archive bucket; and
- budget, account-continuity, monitoring, legal-hold, and incident ownership.

Object Lock protects individual object versions. A later write to the same key could otherwise
create another version, so the adapter's conditional write and restrictive bucket policy remain
mandatory even in `COMPLIANCE` mode.

## Writer permissions

Scope permissions to the dedicated bucket prefix and exact KMS key. The initial adapter needs only:

- `s3:ListBucketVersions` constrained to the deterministic prefix;
- `s3:PutObject` and `s3:PutObjectRetention` for the deterministic prefix;
- `s3:GetObjectVersion` and `s3:GetObjectRetention` for exact-version verification;
- `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey`, and `kms:DescribeKey` on the archive key; and
- the identity provider's permission to assume the dedicated role.

Do not grant `s3:DeleteObject`, `s3:DeleteObjectVersion`,
`s3:BypassGovernanceRetention`, bucket/lifecycle/policy administration,
`s3:PutObjectLegalHold`, KMS key administration, IAM administration, or audit administration.
Production policy simulation must prove these denials before the first export.

Routine CI uses Terraform's mock provider and `command = plan`; it has no AWS credential,
`id-token: write`, backend initialization, or apply path. See the foundation README for the
controlled two-reviewer live sequence.

After an approved deployment, run the [read-only foundation audit](aws-archive-foundation-audit.md)
from a separately authorized operator identity. It verifies observed S3, KMS, IAM/OIDC, and
CloudTrail configuration but performs no upload, mutation, IAM simulation, or restore.

## CLI contract

The CLI uses the standard AWS credential chain. Do not pass access keys on the command line or
store them in repository variables.

```text
python tools/export_archive_to_s3.py \
  --archive atep-release-evidence.zip \
  --local-receipt release-archive-receipt.json \
  --bucket <approved-object-lock-bucket> \
  --expected-bucket-owner <12-digit-account-id> \
  --kms-key-arn <exact-kms-key-arn> \
  --retain-until 2040-08-11T00:00:00Z \
  --region eu-west-1 \
  --output-directory export-evidence
```

`retain-until` is an explicit policy input, not a convenient default. Because `COMPLIANCE`
retention cannot be shortened, the first live exercise must use a disposable evidence object and a
retention duration approved for the test account.

## Live acceptance sequence

1. Audit account, bucket, versioning, Object Lock, KMS, CloudTrail, OIDC trust, and role policies.
2. Run IAM policy simulation proving allowed operations and every forbidden administration/delete
   operation.
3. Export one disposable sealed archive with an approved retention deadline.
4. Retain the S3 request correlation, CloudTrail event, object version, retention metadata, KMS
   evidence, provider evidence, and normalized export receipt.
5. Attempt the same deterministic key again and require a conditional-write failure without a new
   version.
6. Prove the writer cannot delete the version, shorten retention, bypass retention, alter the bucket
   policy, administer the KMS key, or modify audit configuration.
7. Use the separate restore role to download the exact version on a clean host and complete offline
   attestation verification.
8. Confirm alarms, inventory/catalogue registration, cost ownership, and scheduled restore.

## References

- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Uploading Object Lock objects](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html)
- [Boto3 PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html)
- [Boto3 HeadObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/head_object.html)
- [Boto3 GetObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html)
- [Boto3 GetCallerIdentity](https://docs.aws.amazon.com/boto3/latest/reference/services/sts/client/get_caller_identity.html)
