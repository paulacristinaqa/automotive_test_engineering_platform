from __future__ import annotations

import argparse
import importlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import unquote

from tools.export_archive_to_s3 import (
    validate_bucket_name,
    validate_expected_owner,
    validate_kms_key_arn,
)

SCHEMA_VERSION = "1.0.0"
REPORT_NAME = "atep-aws-archive-foundation-audit.json"
ARCHIVE_PREFIX = "atep/releases/"
WRITER_POLICY = "atep-immutable-archive-write"
RESTORE_POLICY = "atep-immutable-archive-read"
FORBIDDEN_ACTION_FRAGMENTS = (
    "delete",
    "bypassgovernanceretention",
    "putobjectlegalhold",
    "putbucket",
    "iam:",
    "cloudtrail:",
    "kms:create",
    "kms:disable",
    "kms:enable",
    "kms:put",
    "kms:schedule",
    "kms:tag",
    "kms:untag",
    "kms:update",
)


class AwsClient(Protocol):
    def __getattr__(self, name: str) -> Callable[..., Mapping[str, Any]]: ...


@dataclass(frozen=True)
class AuditCheck:
    check_id: str
    status: str
    summary: str


@dataclass(frozen=True)
class AuditReport:
    schema_version: str
    status: str
    checked_at: str
    archive_account_id: str
    region: str
    archive_bucket: str
    archive_kms_key_arn: str
    writer_role: str
    restore_role: str
    cloudtrail_arn: str
    checks: tuple[AuditCheck, ...]


def _require(condition: bool, *, check_id: str, summary: str) -> AuditCheck:
    if not condition:
        raise ValueError(f"{check_id} failed: {summary}")
    return AuditCheck(check_id=check_id, status="passed", summary=summary)


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _policy_document(value: object, *, label: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(unquote(value))
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError(f"{label} is not valid JSON") from error
    return _require_mapping(value, label=label)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if all(isinstance(item, str) for item in value):
            return tuple(value)
    return ()


def _policy_actions(document: Mapping[str, Any]) -> set[str]:
    statements = document.get("Statement")
    if not isinstance(statements, Sequence) or isinstance(statements, (str, bytes)):
        raise ValueError("IAM policy Statement must be a list")
    actions: set[str] = set()
    for statement in statements:
        mapping = _require_mapping(statement, label="IAM policy statement")
        if mapping.get("Effect") == "Allow":
            actions.update(action.lower() for action in _strings(mapping.get("Action")))
    return actions


def _audit_role(
    iam: AwsClient,
    *,
    role_name: str,
    policy_name: str,
    expected_subject: str,
    expected_provider_arn: str,
    required_actions: set[str],
) -> tuple[AuditCheck, AuditCheck]:
    response = iam.get_role(RoleName=role_name)
    role = _require_mapping(response.get("Role"), label=f"IAM role {role_name}")
    trust = _policy_document(
        role.get("AssumeRolePolicyDocument"), label=f"IAM role {role_name} trust policy"
    )
    statements = trust.get("Statement")
    statement = (
        _require_mapping(statements[0], label=f"IAM role {role_name} trust statement")
        if isinstance(statements, Sequence)
        and not isinstance(statements, (str, bytes))
        and len(statements) == 1
        else {}
    )
    principal = _require_mapping(statement.get("Principal", {}), label="OIDC principal")
    conditions = _require_mapping(statement.get("Condition", {}), label="OIDC conditions")
    string_equals = _require_mapping(
        conditions.get("StringEquals", {}), label="OIDC StringEquals conditions"
    )
    trust_ok = (
        role.get("MaxSessionDuration") == 3600
        and statement.get("Effect") == "Allow"
        and principal == {"Federated": expected_provider_arn}
        and statement.get("Action") == "sts:AssumeRoleWithWebIdentity"
        and string_equals.get("token.actions.githubusercontent.com:aud") == "sts.amazonaws.com"
        and string_equals.get("token.actions.githubusercontent.com:sub") == expected_subject
        and all("*" not in value for value in string_equals.values() if isinstance(value, str))
        and not (set(conditions) - {"StringEquals"})
    )
    trust_check = _require(
        trust_ok,
        check_id=f"iam-{policy_name}-trust",
        summary="role uses the exact OIDC provider/subject and a 3,600-second session",
    )

    attached = iam.list_attached_role_policies(RoleName=role_name, MaxItems=100)
    inline = iam.list_role_policies(RoleName=role_name, MaxItems=100)
    policy_names = _strings(inline.get("PolicyNames"))
    if attached.get("IsTruncated") or inline.get("IsTruncated"):
        raise ValueError(f"IAM role {role_name} policy listing was unexpectedly truncated")
    policy = iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
    actions = _policy_actions(
        _policy_document(policy.get("PolicyDocument"), label=f"IAM policy {policy_name}")
    )
    forbidden = any(
        fragment in action for action in actions for fragment in FORBIDDEN_ACTION_FRAGMENTS
    )
    policy_check = _require(
        not attached.get("AttachedPolicies")
        and policy_names == (policy_name,)
        and actions == {action.lower() for action in required_actions}
        and not forbidden,
        check_id=f"iam-{policy_name}-least-privilege",
        summary="role has one exact inline data-plane policy and no managed or forbidden authority",
    )
    return trust_check, policy_check


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("audit report already exists; replacement is forbidden")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def audit_aws_archive_foundation(
    *,
    s3: AwsClient,
    kms: AwsClient,
    iam: AwsClient,
    sts: AwsClient,
    cloudtrail: AwsClient,
    account_id: str,
    region: str,
    bucket: str,
    kms_key_arn: str,
    writer_role: str,
    restore_role: str,
    writer_subject: str,
    restore_subject: str,
    oidc_provider_arn: str,
    trail_arn: str,
    audit_bucket: str,
    audit_kms_key_arn: str,
    minimum_retention_days: int,
    output_path: Path,
    clock: Callable[[], datetime] | None = None,
) -> AuditReport:
    account_id = validate_expected_owner(account_id)
    bucket = validate_bucket_name(bucket)
    validate_bucket_name(audit_bucket)
    kms_key_arn = validate_kms_key_arn(kms_key_arn, expected_owner=account_id)
    if not 365 <= minimum_retention_days <= 36500:
        raise ValueError("minimum retention must be between 365 and 36500 days")
    if bucket == audit_bucket:
        raise ValueError("audit storage must remain separate from archive storage")
    if writer_role == restore_role or writer_subject == restore_subject:
        raise ValueError("writer and restore identities must remain distinct")
    if not trail_arn.startswith(f"arn:aws:cloudtrail:{region}:{account_id}:trail/"):
        raise ValueError("CloudTrail ARN must belong to the expected account and region")

    checks: list[AuditCheck] = []
    caller = sts.get_caller_identity()
    checks.append(
        _require(
            caller.get("Account") == account_id,
            check_id="identity-account",
            summary="caller belongs to the explicitly expected archive account",
        )
    )

    versioning = s3.get_bucket_versioning(Bucket=bucket, ExpectedBucketOwner=account_id)
    lock = _require_mapping(
        s3.get_object_lock_configuration(Bucket=bucket, ExpectedBucketOwner=account_id).get(
            "ObjectLockConfiguration"
        ),
        label="S3 Object Lock configuration",
    )
    rule = _require_mapping(lock.get("Rule"), label="S3 Object Lock rule")
    retention = _require_mapping(rule.get("DefaultRetention"), label="default retention")
    checks.append(
        _require(
            versioning.get("Status") == "Enabled"
            and lock.get("ObjectLockEnabled") == "Enabled"
            and retention.get("Mode") == "COMPLIANCE"
            and isinstance(retention.get("Days"), int)
            and retention["Days"] >= minimum_retention_days,
            check_id="s3-immutability",
            summary="versioning and Object Lock COMPLIANCE retention meet the approved minimum",
        )
    )

    encryption = s3.get_bucket_encryption(Bucket=bucket, ExpectedBucketOwner=account_id)
    rules = _require_mapping(encryption, label="S3 encryption").get(
        "ServerSideEncryptionConfiguration", {"Rules": []}
    )
    rules_mapping = _require_mapping(rules, label="S3 encryption configuration")
    encryption_rules = rules_mapping.get("Rules")
    encryption_ok = False
    if isinstance(encryption_rules, Sequence):
        for item in encryption_rules:
            rule_value = _require_mapping(item, label="S3 encryption rule")
            default = _require_mapping(
                rule_value.get("ApplyServerSideEncryptionByDefault"),
                label="S3 default encryption",
            )
            encryption_ok = encryption_ok or (
                default.get("SSEAlgorithm") == "aws:kms"
                and default.get("KMSMasterKeyID") == kms_key_arn
                and rule_value.get("BucketKeyEnabled") is True
            )
    checks.append(
        _require(
            encryption_ok,
            check_id="s3-encryption",
            summary="default encryption uses the exact customer KMS key and Bucket Key",
        )
    )

    public = s3.get_public_access_block(Bucket=bucket, ExpectedBucketOwner=account_id)
    public_config = _require_mapping(
        public.get("PublicAccessBlockConfiguration"), label="S3 public access block"
    )
    ownership = s3.get_bucket_ownership_controls(Bucket=bucket, ExpectedBucketOwner=account_id)
    ownership_rules = _require_mapping(ownership, label="S3 ownership controls").get("Rules")
    ownership_ok = isinstance(ownership_rules, Sequence) and any(
        isinstance(item, Mapping) and item.get("ObjectOwnership") == "BucketOwnerEnforced"
        for item in ownership_rules
    )
    checks.append(
        _require(
            all(
                public_config.get(field) is True
                for field in (
                    "BlockPublicAcls",
                    "IgnorePublicAcls",
                    "BlockPublicPolicy",
                    "RestrictPublicBuckets",
                )
            )
            and ownership_ok,
            check_id="s3-private-ownership",
            summary="all public access is blocked and ownership is bucket-owner enforced",
        )
    )

    bucket_policy = _policy_document(
        s3.get_bucket_policy(Bucket=bucket, ExpectedBucketOwner=account_id).get("Policy"),
        label="S3 bucket policy",
    )
    policy_sids = {
        statement.get("Sid")
        for statement in bucket_policy.get("Statement", [])
        if isinstance(statement, Mapping) and statement.get("Effect") == "Deny"
    }
    required_sids = {
        "DenyInsecureTransport",
        "DenyOldTLS",
        "DenyObjectsOutsideFixedPrefix",
        "DenyMissingOrWrongEncryption",
        "DenyWrongKMSKey",
        "DenyNonComplianceRetention",
        "DenyRetentionBelowMinimum",
    }
    checks.append(
        _require(
            required_sids <= policy_sids
            and kms_key_arn in json.dumps(bucket_policy)
            and ARCHIVE_PREFIX in json.dumps(bucket_policy),
            check_id="s3-deny-policy",
            summary=(
                "bucket policy contains every named deny guard for TLS, prefix, KMS, and retention"
            ),
        )
    )

    key = _require_mapping(kms.describe_key(KeyId=kms_key_arn).get("KeyMetadata"), label="KMS key")
    rotation = kms.get_key_rotation_status(KeyId=kms_key_arn)
    checks.append(
        _require(
            key.get("Arn") == kms_key_arn
            and key.get("AWSAccountId") == account_id
            and key.get("Enabled") is True
            and key.get("KeyState") == "Enabled"
            and key.get("KeyUsage") == "ENCRYPT_DECRYPT"
            and key.get("KeySpec") == "SYMMETRIC_DEFAULT"
            and key.get("KeyManager") == "CUSTOMER"
            and rotation.get("KeyRotationEnabled") is True
            and rotation.get("RotationPeriodInDays") == 365,
            check_id="kms-key",
            summary="customer symmetric encryption key is enabled with 365-day automatic rotation",
        )
    )

    checks.extend(
        _audit_role(
            iam,
            role_name=writer_role,
            policy_name=WRITER_POLICY,
            expected_subject=writer_subject,
            expected_provider_arn=oidc_provider_arn,
            required_actions={
                "s3:ListBucketVersions",
                "s3:GetObjectRetention",
                "s3:GetObjectVersion",
                "s3:PutObject",
                "s3:PutObjectRetention",
                "kms:Decrypt",
                "kms:DescribeKey",
                "kms:Encrypt",
                "kms:GenerateDataKey",
            },
        )
    )
    checks.extend(
        _audit_role(
            iam,
            role_name=restore_role,
            policy_name=RESTORE_POLICY,
            expected_subject=restore_subject,
            expected_provider_arn=oidc_provider_arn,
            required_actions={
                "s3:GetObjectRetention",
                "s3:GetObjectVersion",
                "kms:Decrypt",
                "kms:DescribeKey",
            },
        )
    )

    trail = _require_mapping(cloudtrail.get_trail(Name=trail_arn).get("Trail"), label="CloudTrail")
    status = cloudtrail.get_trail_status(Name=trail_arn)
    selectors = cloudtrail.get_event_selectors(TrailName=trail_arn)
    selector_json = json.dumps(selectors.get("AdvancedEventSelectors", []), sort_keys=True)
    checks.append(
        _require(
            trail.get("TrailARN") == trail_arn
            and trail.get("S3BucketName") == audit_bucket
            and trail.get("KmsKeyId") == audit_kms_key_arn
            and trail.get("IncludeGlobalServiceEvents") is True
            and trail.get("IsMultiRegionTrail") is True
            and trail.get("LogFileValidationEnabled") is True
            and status.get("IsLogging") is True
            and not status.get("LatestDeliveryError")
            and not status.get("LatestDigestDeliveryError")
            and "Management" in selector_json
            and "AWS::S3::Object" in selector_json
            and f"arn:aws:s3:::{bucket}/" in selector_json,
            check_id="cloudtrail-audit",
            summary=(
                "validated multi-Region trail is logging management and archive object events "
                "externally"
            ),
        )
    )

    now = (clock or (lambda: datetime.now(UTC)))()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("audit clock must be timezone-aware")
    report = AuditReport(
        schema_version=SCHEMA_VERSION,
        status="passed",
        checked_at=now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        archive_account_id=account_id,
        region=region,
        archive_bucket=bucket,
        archive_kms_key_arn=kms_key_arn,
        writer_role=writer_role,
        restore_role=restore_role,
        cloudtrail_arn=trail_arn,
        checks=tuple(checks),
    )
    _atomic_write(output_path, asdict(report))
    return report


def create_clients(*, region: str) -> tuple[AwsClient, AwsClient, AwsClient, AwsClient, AwsClient]:
    try:
        boto3 = importlib.import_module("boto3")
    except ImportError as error:
        raise RuntimeError("boto3 is required for the AWS foundation auditor") from error
    session = boto3.session.Session(region_name=region)
    return (
        session.client("s3"),
        session.client("kms"),
        session.client("iam"),
        session.client("sts"),
        session.client("cloudtrail"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only audit of an ATEP AWS archive foundation."
    )
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--kms-key-arn", required=True)
    parser.add_argument("--writer-role", required=True)
    parser.add_argument("--restore-role", required=True)
    parser.add_argument("--writer-subject", required=True)
    parser.add_argument("--restore-subject", required=True)
    parser.add_argument("--oidc-provider-arn", required=True)
    parser.add_argument("--trail-arn", required=True)
    parser.add_argument("--audit-bucket", required=True)
    parser.add_argument("--audit-kms-key-arn", required=True)
    parser.add_argument("--minimum-retention-days", type=int, default=3650)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    s3, kms, iam, sts, cloudtrail = create_clients(region=args.region)
    audit_aws_archive_foundation(
        s3=s3,
        kms=kms,
        iam=iam,
        sts=sts,
        cloudtrail=cloudtrail,
        account_id=args.account_id,
        region=args.region,
        bucket=args.bucket,
        kms_key_arn=args.kms_key_arn,
        writer_role=args.writer_role,
        restore_role=args.restore_role,
        writer_subject=args.writer_subject,
        restore_subject=args.restore_subject,
        oidc_provider_arn=args.oidc_provider_arn,
        trail_arn=args.trail_arn,
        audit_bucket=args.audit_bucket,
        audit_kms_key_arn=args.audit_kms_key_arn,
        minimum_retention_days=args.minimum_retention_days,
        output_path=args.output.resolve(),
    )


if __name__ == "__main__":
    main()
