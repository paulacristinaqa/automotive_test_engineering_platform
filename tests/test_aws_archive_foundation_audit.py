from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tools.audit_aws_archive_foundation import (
    REPORT_NAME,
    audit_aws_archive_foundation,
)

ACCOUNT = "123456789012"
REGION = "eu-west-1"
BUCKET = "atep-immutable-release-evidence"
AUDIT_BUCKET = "atep-independent-audit-logs"
KMS_ARN = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/12345678-1234-1234-1234-1234567890ab"
AUDIT_KMS_ARN = f"arn:aws:kms:{REGION}:999999999999:key/audit-key"
OIDC_ARN = f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"
TRAIL_ARN = f"arn:aws:cloudtrail:{REGION}:{ACCOUNT}:trail/atep-immutable-archive"
WRITER_SUBJECT = (
    "repo:paulacristinaqa/automotive_test_engineering_platform:environment:archive-write"
)
RESTORE_SUBJECT = (
    "repo:paulacristinaqa/automotive_test_engineering_platform:environment:archive-restore"
)


class FakeSts:
    account = ACCOUNT

    def get_caller_identity(self) -> dict[str, Any]:
        return {"Account": self.account, "Arn": "redacted-by-report", "UserId": "session"}


class FakeS3:
    retention_days = 3650
    kms_key_arn = KMS_ARN
    policy_sids = (
        "DenyInsecureTransport",
        "DenyOldTLS",
        "DenyObjectsOutsideFixedPrefix",
        "DenyMissingOrWrongEncryption",
        "DenyWrongKMSKey",
        "DenyNonComplianceRetention",
        "DenyRetentionBelowMinimum",
    )

    def get_bucket_versioning(self, **kwargs: object) -> dict[str, Any]:
        return {"Status": "Enabled"}

    def get_object_lock_configuration(self, **kwargs: object) -> dict[str, Any]:
        return {
            "ObjectLockConfiguration": {
                "ObjectLockEnabled": "Enabled",
                "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": self.retention_days}},
            }
        }

    def get_bucket_encryption(self, **kwargs: object) -> dict[str, Any]:
        return {
            "ServerSideEncryptionConfiguration": {
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "aws:kms",
                            "KMSMasterKeyID": self.kms_key_arn,
                        },
                        "BucketKeyEnabled": True,
                    }
                ]
            }
        }

    def get_public_access_block(self, **kwargs: object) -> dict[str, Any]:
        return {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            }
        }

    def get_bucket_ownership_controls(self, **kwargs: object) -> dict[str, Any]:
        return {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}

    def get_bucket_policy(self, **kwargs: object) -> dict[str, Any]:
        statements = [
            {"Sid": sid, "Effect": "Deny", "Resource": [KMS_ARN, "atep/releases/"]}
            for sid in self.policy_sids
        ]
        return {"Policy": json.dumps({"Version": "2012-10-17", "Statement": statements})}


class FakeKms:
    rotation_enabled = True

    def describe_key(self, **kwargs: object) -> dict[str, Any]:
        return {
            "KeyMetadata": {
                "Arn": KMS_ARN,
                "AWSAccountId": ACCOUNT,
                "Enabled": True,
                "KeyState": "Enabled",
                "KeyUsage": "ENCRYPT_DECRYPT",
                "KeySpec": "SYMMETRIC_DEFAULT",
                "KeyManager": "CUSTOMER",
            }
        }

    def get_key_rotation_status(self, **kwargs: object) -> dict[str, Any]:
        return {"KeyRotationEnabled": self.rotation_enabled, "RotationPeriodInDays": 365}


class FakeIam:
    writer_actions = {
        "s3:ListBucketVersions",
        "s3:GetObjectRetention",
        "s3:GetObjectVersion",
        "s3:PutObject",
        "s3:PutObjectRetention",
        "kms:Decrypt",
        "kms:DescribeKey",
        "kms:Encrypt",
        "kms:GenerateDataKey",
    }
    restore_actions = {
        "s3:GetObjectRetention",
        "s3:GetObjectVersion",
        "kms:Decrypt",
        "kms:DescribeKey",
    }
    extra_action: str | None = None

    def get_role(self, *, RoleName: str) -> dict[str, Any]:
        subject = WRITER_SUBJECT if RoleName == "atep-archive-writer" else RESTORE_SUBJECT
        return {
            "Role": {
                "MaxSessionDuration": 3600,
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Federated": OIDC_ARN},
                            "Action": "sts:AssumeRoleWithWebIdentity",
                            "Condition": {
                                "StringEquals": {
                                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                                    "token.actions.githubusercontent.com:sub": subject,
                                }
                            },
                        }
                    ],
                },
            }
        }

    def list_attached_role_policies(self, **kwargs: object) -> dict[str, Any]:
        return {"AttachedPolicies": [], "IsTruncated": False}

    def list_role_policies(self, *, RoleName: str, **kwargs: object) -> dict[str, Any]:
        name = (
            "atep-immutable-archive-write"
            if RoleName == "atep-archive-writer"
            else "atep-immutable-archive-read"
        )
        return {"PolicyNames": [name], "IsTruncated": False}

    def get_role_policy(self, *, RoleName: str, **kwargs: object) -> dict[str, Any]:
        actions = set(
            self.writer_actions if RoleName == "atep-archive-writer" else self.restore_actions
        )
        if self.extra_action:
            actions.add(self.extra_action)
        return {
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Action": sorted(actions), "Resource": "*"}],
            }
        }


class FakeCloudTrail:
    logging = True

    def get_trail(self, **kwargs: object) -> dict[str, Any]:
        return {
            "Trail": {
                "TrailARN": TRAIL_ARN,
                "S3BucketName": AUDIT_BUCKET,
                "KmsKeyId": AUDIT_KMS_ARN,
                "IncludeGlobalServiceEvents": True,
                "IsMultiRegionTrail": True,
                "LogFileValidationEnabled": True,
            }
        }

    def get_trail_status(self, **kwargs: object) -> dict[str, Any]:
        return {"IsLogging": self.logging}

    def get_event_selectors(self, **kwargs: object) -> dict[str, Any]:
        return {
            "AdvancedEventSelectors": [
                {"FieldSelectors": [{"Field": "eventCategory", "Equals": ["Management"]}]},
                {
                    "FieldSelectors": [
                        {"Field": "resources.type", "Equals": ["AWS::S3::Object"]},
                        {"Field": "resources.ARN", "StartsWith": [f"arn:aws:s3:::{BUCKET}/"]},
                    ]
                },
            ]
        }


def run_audit(tmp_path: Path, **overrides: object) -> Path:
    output = tmp_path / REPORT_NAME
    values: dict[str, object] = {
        "s3": FakeS3(),
        "kms": FakeKms(),
        "iam": FakeIam(),
        "sts": FakeSts(),
        "cloudtrail": FakeCloudTrail(),
        "account_id": ACCOUNT,
        "region": REGION,
        "bucket": BUCKET,
        "kms_key_arn": KMS_ARN,
        "writer_role": "atep-archive-writer",
        "restore_role": "atep-archive-restore",
        "writer_subject": WRITER_SUBJECT,
        "restore_subject": RESTORE_SUBJECT,
        "oidc_provider_arn": OIDC_ARN,
        "trail_arn": TRAIL_ARN,
        "audit_bucket": AUDIT_BUCKET,
        "audit_kms_key_arn": AUDIT_KMS_ARN,
        "minimum_retention_days": 3650,
        "output_path": output,
        "clock": lambda: datetime(2026, 8, 12, 10, 0, tzinfo=UTC),
    }
    values.update(overrides)
    audit_aws_archive_foundation(**values)  # type: ignore[arg-type]
    return output


def test_read_only_audit_emits_bounded_non_sensitive_evidence(tmp_path: Path) -> None:
    output = run_audit(tmp_path)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert report["schema_version"] == "1.0.0"
    assert len(report["checks"]) == 11
    assert all(check["status"] == "passed" for check in report["checks"])
    serialized = output.read_text(encoding="utf-8").lower()
    assert "redacted-by-report" not in serialized
    assert "userid" not in serialized
    assert "policydocument" not in serialized


@pytest.mark.parametrize(
    ("client_name", "mutation", "message"),
    [
        ("sts", lambda client: setattr(client, "account", "999999999999"), "identity-account"),
        ("s3", lambda client: setattr(client, "retention_days", 3649), "s3-immutability"),
        ("s3", lambda client: setattr(client, "kms_key_arn", KMS_ARN + "-wrong"), "s3-encryption"),
        ("kms", lambda client: setattr(client, "rotation_enabled", False), "kms-key"),
        (
            "iam",
            lambda client: setattr(client, "extra_action", "s3:DeleteObject"),
            "least-privilege",
        ),
        ("cloudtrail", lambda client: setattr(client, "logging", False), "cloudtrail-audit"),
    ],
)
def test_audit_fails_closed_without_writing_partial_evidence(
    tmp_path: Path, client_name: str, mutation: Any, message: str
) -> None:
    clients = {
        "s3": FakeS3(),
        "kms": FakeKms(),
        "iam": FakeIam(),
        "sts": FakeSts(),
        "cloudtrail": FakeCloudTrail(),
    }
    mutation(clients[client_name])
    with pytest.raises(ValueError, match=message):
        run_audit(tmp_path, **clients)
    assert not (tmp_path / REPORT_NAME).exists()


def test_audit_rejects_shared_control_boundaries_before_aws_calls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="audit storage must remain separate"):
        run_audit(tmp_path, audit_bucket=BUCKET)
    with pytest.raises(ValueError, match="identities must remain distinct"):
        run_audit(tmp_path, restore_subject=WRITER_SUBJECT)


def test_audit_report_is_non_replacing(tmp_path: Path) -> None:
    output = run_audit(tmp_path)
    with pytest.raises(ValueError, match="replacement is forbidden"):
        run_audit(tmp_path)
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"


def test_auditor_contains_no_aws_mutation_or_role_assumption() -> None:
    source = (Path("tools") / "audit_aws_archive_foundation.py").read_text(encoding="utf-8")
    forbidden_calls = {
        ".assume_role(",
        ".assume_role_with_web_identity(",
        ".put_object(",
        ".put_object_retention(",
        ".put_bucket",
        ".start_logging(",
        ".stop_logging(",
        ".update_trail(",
        ".enable_key",
        ".disable_key",
        ".terraform",
    }

    assert not any(call in source for call in forbidden_calls)
