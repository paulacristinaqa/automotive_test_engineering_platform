# AWS archive foundation read-only audit

This runbook verifies an already provisioned ATEP immutable archive foundation without creating,
modifying, or deleting AWS resources. It is an operator-controlled acceptance step, not a routine
CI job and not a substitute for independent review, IAM simulation, retained-object denial tests,
CloudTrail event correlation, or clean-host restore.

## Safety boundary

The auditor calls only read operations against STS, S3, KMS, IAM, and CloudTrail. It:

1. requires an explicit 12-digit account, Region, bucket, KMS key ARN, role names, exact GitHub
   OIDC subjects, trail ARN, and independent audit destination;
2. refuses shared writer/restore identities or shared archive/audit buckets before any AWS call;
3. fails on the first absent, ambiguous, truncated, weak, or inconsistent control;
4. writes one non-replacing JSON report only after every check passes; and
5. excludes caller ARN/session ID, raw policies, AWS response bodies, credentials, and tokens.

The process never calls `terraform plan` or `terraform apply`, uploads an object, changes
retention, simulates permissions, starts logging, or assumes another role. Its current credentials
must therefore be a separately approved read-only audit identity.

## Minimum audit permissions

Grant only the exact resources where the AWS API supports resource scoping. The operator identity
needs the following read actions:

- `sts:GetCallerIdentity`;
- `s3:GetBucketVersioning`, `s3:GetBucketObjectLockConfiguration`,
  `s3:GetEncryptionConfiguration`, `s3:GetBucketPublicAccessBlock`,
  `s3:GetBucketOwnershipControls`, and `s3:GetBucketPolicy`;
- `kms:DescribeKey` and `kms:GetKeyRotationStatus` on the archive key;
- `iam:GetRole`, `iam:ListAttachedRolePolicies`, `iam:ListRolePolicies`, and
  `iam:GetRolePolicy` for the writer and restore roles; and
- `cloudtrail:GetTrail`, `cloudtrail:GetTrailStatus`, and `cloudtrail:GetEventSelectors` for the
  archive trail.

Do not give this identity S3 object write/read, retention administration, KMS cryptographic or
administrative operations, IAM mutation, CloudTrail mutation, or Terraform state access.

## Controlled execution

Use an approved operator workstation and a short-lived read-only AWS session. Do not put access
keys in arguments or repository files. Populate exact values from the independently reviewed
Terraform plan and AWS console/API evidence, then run:

```powershell
python .\tools\audit_aws_archive_foundation.py `
  --account-id 123456789012 `
  --region eu-west-1 `
  --bucket atep-example-immutable-archive `
  --kms-key-arn arn:aws:kms:eu-west-1:123456789012:key/00000000-0000-0000-0000-000000000000 `
  --writer-role atep-archive-writer `
  --restore-role atep-archive-restore `
  --writer-subject repo:paulacristinaqa/automotive_test_engineering_platform:environment:archive-write `
  --restore-subject repo:paulacristinaqa/automotive_test_engineering_platform:environment:archive-restore `
  --oidc-provider-arn arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com `
  --trail-arn arn:aws:cloudtrail:eu-west-1:123456789012:trail/atep-immutable-archive `
  --audit-bucket independently-governed-audit-example `
  --audit-kms-key-arn arn:aws:kms:eu-west-1:999999999999:key/11111111-1111-1111-1111-111111111111 `
  --minimum-retention-days 3650 `
  --output .\evidence\atep-aws-archive-foundation-audit.json
```

All names above are placeholders. Never copy them into a live command without replacing and
reviewing every value.

## Acceptance checks

The report is emitted only when all checks pass:

- caller account equals the explicitly expected archive account;
- bucket versioning and Object Lock are enabled with default `COMPLIANCE` days at or above the
  approved minimum;
- default encryption uses the exact customer-managed KMS key and Bucket Key;
- all four S3 public-access controls and bucket-owner-enforced ownership are active;
- the bucket policy contains the reviewed named deny controls for TLS, prefix, KMS, mode, and
  minimum retention;
- the KMS key is enabled, customer managed, symmetric, encryption-only, and rotates every 365
  days;
- writer and restore roles have exact wildcard-free OIDC trust, 3,600-second sessions, one exact
  inline policy, no attached managed policies, and only the expected data-plane actions; and
- CloudTrail is enabled, validated, multi-Region, free of current delivery errors, externally
  delivered, and selects management plus archive S3 object data events.

## Remaining live evidence

A passed report proves only the observed configuration at one UTC instant. Before production,
retain independent evidence for effective IAM allow/deny simulation, environment reviewer rules,
first immutable upload, repeat-write and destructive-operation denials, retention-shortening and
bypass denials, matching CloudTrail delivery, exact-version read-back, and clean-host restore.

