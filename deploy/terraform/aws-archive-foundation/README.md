# AWS immutable archive foundation

This Terraform root module defines the production foundation required by the ATEP S3 Object Lock
adapter. It is intentionally **not** applied by CI and contains no credentials, account IDs, bucket
names, or backend values for a real environment.

## Ownership boundary

The module creates and owns:

- one new general-purpose S3 bucket with Object Lock enabled at creation time;
- enabled versioning, blocked public access, bucket-owner enforcement, and default SSE-KMS;
- a non-destroyable regional KMS key with annual rotation and a 30-day deletion window;
- default and minimum `COMPLIANCE` retention;
- a short-lived archive-writer role and a distinct read-only restore role;
- bucket policy denials for insecure transport, old TLS, the wrong prefix, weak encryption, the
  wrong KMS key, non-compliance retention, and retention below the approved minimum; and
- a multi-Region CloudTrail with log-file validation, management events, and all object data events
  for the archive bucket.

The module deliberately does **not** create:

- the AWS account;
- the account-wide GitHub OIDC provider;
- KMS administrator roles;
- the CloudTrail destination bucket or its KMS key; or
- the remote Terraform state backend.

Those controls must already exist under separate administration. The CloudTrail destination owner
must grant the trail service the documented bucket and KMS permissions before this module is
applied. Keeping audit storage and state outside the archive boundary prevents the writer or this
stack from rewriting its own control evidence.

## Identity contract

Both roles trust the official GitHub Actions OIDC provider, require audience
`sts.amazonaws.com`, and accept one exact `sub` value without wildcards. Writer and restore subjects
must differ. Before a live plan, capture the repository's actual OIDC claims and confirm whether it
uses GitHub's legacy or immutable owner/repository-ID subject format. Protect both GitHub
environments, restrict deployment branches to `main`, require independent approval, and disable
self-review and administrator bypass.

The writer can list version history under `atep/releases/`, upload with retention, and read the
returned version. It can use the archive key only for encryption and verification. The restore role
can read and decrypt exact versions. Neither policy contains delete, retention bypass, legal-hold,
bucket, IAM, KMS-administration, or CloudTrail-administration permissions.

## Safe validation

The repository CI runs only formatting, initialization without a backend, validation, and a mocked
plan test:

```text
terraform fmt -check -recursive deploy/terraform
terraform -chdir=deploy/terraform/aws-archive-foundation init -backend=false -lockfile=readonly
terraform -chdir=deploy/terraform/aws-archive-foundation validate
terraform -chdir=deploy/terraform/aws-archive-foundation test
```

The test uses `mock_provider "aws"` and `command = plan`; it cannot contact AWS or create billable
resources. Do not change it to `command = apply` in routine CI.

## Controlled live sequence

1. Independently review account ownership, GitHub environment settings, OIDC claims, KMS
   administrators, audit bucket/KMS policies, budget, and remote-state controls.
2. Copy `terraform.tfvars.example` outside version control and replace every placeholder.
3. Initialize the separately encrypted and locked remote backend; never store production state in
   the archive bucket or in GitHub artifacts.
4. Run and retain `terraform plan -out=<approved-plan>` using short-lived provisioning credentials.
5. Have a second authorized reviewer inspect the exact plan, provider lock, policies, destructive
   flags, costs, and retention duration.
6. Apply only the approved saved plan in a protected environment. Object Lock and retained
   `COMPLIANCE` versions cannot be casually undone.
7. Record the outputs in the controlled configuration catalogue, never in public logs if account
   policy classifies them as sensitive.
8. Complete the adapter's live upload, repeat-write denial, delete/shorten/bypass denial,
   CloudTrail correlation, and clean-host restore acceptance sequence.

## References

- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Configuring S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-configure.html)
- [S3 Object Lock considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html)
- [CloudTrail data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html)
- [AWS IAM GitHub OIDC guidance](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html)
- [GitHub OIDC reference](https://docs.github.com/en/actions/reference/security/oidc)
- [Terraform validate](https://developer.hashicorp.com/terraform/cli/commands/validate)
- [Terraform test](https://developer.hashicorp.com/terraform/cli/commands/test)
