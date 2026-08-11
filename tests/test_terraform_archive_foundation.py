from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).parents[1]
FOUNDATION = ROOT / "deploy" / "terraform" / "aws-archive-foundation"


def read(name: str) -> str:
    return (FOUNDATION / name).read_text(encoding="utf-8")


def test_archive_foundation_is_complete_pinned_and_has_no_live_values() -> None:
    expected = {
        "README.md",
        "audit.tf",
        "identity.tf",
        "locals.tf",
        "outputs.tf",
        "storage.tf",
        "terraform.tfvars.example",
        "variables.tf",
        "versions.tf",
    }
    assert expected <= {path.name for path in FOUNDATION.iterdir() if path.is_file()}

    versions = read("versions.tf")
    assert 'required_version = "~> 1.15.0"' in versions
    assert 'version = "6.58.0"' in versions
    assert 'backend "s3" {}' in versions
    assert "allowed_account_ids = [var.archive_account_id]" in versions

    for content in (read("terraform.tfvars.example"), read("variables.tf")):
        assert "AKIA" not in content
        assert "aws_access_key" not in content
        assert "aws_secret" not in content


def test_storage_is_non_destroyable_private_versioned_locked_and_kms_encrypted() -> None:
    storage = read("storage.tf")
    assert storage.count("prevent_destroy = true") == 2
    assert "force_destroy       = false" in storage
    assert "object_lock_enabled = true" in storage
    assert 'status = "Enabled"' in storage
    assert 'mode = "COMPLIANCE"' in storage
    assert "days = var.default_retention_days" in storage
    assert 'sse_algorithm     = "aws:kms"' in storage
    assert "bucket_key_enabled = true" in storage
    assert "enable_key_rotation     = true" in storage
    assert "rotation_period_in_days = 365" in storage
    assert "deletion_window_in_days = 30" in storage
    assert 'object_ownership = "BucketOwnerEnforced"' in storage
    assert all(
        value in storage
        for value in (
            "DenyInsecureTransport",
            "DenyOldTLS",
            "DenyObjectsOutsideFixedPrefix",
            "DenyMissingOrWrongEncryption",
            "DenyWrongKMSKey",
            "DenyNonComplianceRetention",
            "DenyRetentionBelowMinimum",
        )
    )


def test_oidc_roles_are_exact_short_lived_separated_and_least_privilege() -> None:
    identity = read("identity.tf")
    locals_file = read("locals.tf")
    assert identity.count('Action = "sts:AssumeRoleWithWebIdentity"') == 2
    assert identity.count("max_session_duration = 3600") == 2
    assert '"token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"' in locals_file
    assert identity.count('"token.actions.githubusercontent.com:sub"') == 2
    assert identity.count("StringLike") == 1  # only the fixed S3 prefix condition
    variables = read("variables.tf")
    assert variables.count("paulacristinaqa(@[0-9]+)?/automotive_test_engineering_platform") == 2
    assert variables.count(":environment:") == 2
    assert "var.writer_oidc_subject" in identity
    assert "var.restore_oidc_subject" in identity
    assert '"s3:ListBucketVersions"' in identity
    assert '"s3:PutObject"' in identity
    assert '"s3:PutObjectRetention"' in identity
    assert identity.count('"s3:GetObjectVersion"') == 2

    forbidden = (
        "s3:BypassGovernanceRetention",
        "s3:DeleteObject",
        "s3:DeleteObjectVersion",
        "s3:PutObjectLegalHold",
        "iam:*",
        "cloudtrail:*",
    )
    assert all(action not in identity for action in forbidden)
    assert 'Action = "s3:*"' not in identity
    assert 'Action = "kms:*"' not in identity


def test_audit_is_external_validated_multi_region_and_covers_object_events() -> None:
    audit = read("audit.tf")
    locals_file = read("locals.tf")
    assert "s3_bucket_name                = var.audit_bucket_name" in audit
    assert "kms_key_id                    = var.audit_kms_key_arn" in audit
    assert "enable_log_file_validation    = true" in audit
    assert "include_global_service_events = true" in audit
    assert "is_multi_region_trail         = true" in audit
    assert 'equals = ["Data"]' in audit
    assert 'equals = ["Management"]' in audit
    assert 'equals = ["AWS::S3::Object"]' in audit
    assert "var.audit_bucket_name != var.archive_bucket_name" in locals_file
    assert 'resource "aws_s3_bucket" "audit"' not in audit


def test_mocked_terraform_test_can_never_apply_resources() -> None:
    test = read("tests/foundation.tftest.hcl")
    assert 'mock_provider "aws" {}' in test
    assert test.count("command = plan") == 5
    assert "command = apply" not in test
    assert "Object Lock must be enabled" in test
    assert "CloudTrail log file validation" in test
    assert test.count("expect_failures") == 4


def test_security_workflow_validates_iac_without_aws_credentials_or_apply() -> None:
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "security.yml").read_text())
    job = workflow["jobs"]["terraform-archive-foundation"]
    assert job["timeout-minutes"] == 10
    setup = next(step for step in job["steps"] if step.get("uses", "").startswith("hashicorp/"))
    assert setup["with"] == {"terraform_version": "1.15.8", "terraform_wrapper": False}
    rendered = str(job)
    assert "init -backend=false -lockfile=readonly" in rendered
    assert " validate" in rendered
    assert " test" in rendered
    assert "terraform apply" not in rendered
    assert "id-token" not in rendered
    assert "AWS_ACCESS_KEY" not in rendered
