from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from tools.build_release_evidence import atomic_write
from tools.seal_release_archive import (
    ARCHIVE_NAME,
    RECEIPT_NAME,
    read_json_object,
    restore_archive,
    validate_receipt,
)
from tools.validate_archive_export import (
    EXPORT_RECEIPT_NAME,
    EXPORT_SCHEMA_VERSION,
    PROVIDER_EVIDENCE_NAME,
    ProviderUploadEvidence,
    build_export_receipt,
    format_utc_timestamp,
    parse_utc_timestamp,
)

AWS_PROVIDER = "aws-s3-object-lock"
CONTENT_TYPE = "application/zip"
MAX_READ_BACK_BYTES = 256 * 1024 * 1024
BUCKET_PATTERN = re.compile(r"(?=.{3,63}\Z)(?!\d+\.\d+\.\d+\.\d+\Z)[a-z0-9][a-z0-9.-]*[a-z0-9]\Z")
ACCOUNT_PATTERN = re.compile(r"\d{12}\Z")
KMS_KEY_ARN_PATTERN = re.compile(r"arn:aws:kms:[a-z0-9-]+:\d{12}:key/[0-9a-fA-F-]{36}\Z")


class S3Client(Protocol):
    def list_object_versions(self, **kwargs: object) -> dict[str, Any]: ...

    def head_object(self, **kwargs: object) -> dict[str, Any]: ...

    def put_object(self, **kwargs: object) -> dict[str, Any]: ...

    def get_object(self, **kwargs: object) -> dict[str, Any]: ...


class StsClient(Protocol):
    def get_caller_identity(self) -> dict[str, Any]: ...


class ReadableBody(Protocol):
    def read(self, amount: int = -1) -> bytes: ...

    def close(self) -> None: ...


def validate_bucket_name(value: str) -> str:
    if BUCKET_PATTERN.fullmatch(value) is None or ".." in value or ".-" in value or "-." in value:
        raise ValueError("bucket must be a canonical general-purpose S3 bucket name")
    return value


def validate_expected_owner(value: str) -> str:
    if ACCOUNT_PATTERN.fullmatch(value) is None:
        raise ValueError("expected bucket owner must be a 12-digit AWS account ID")
    return value


def validate_kms_key_arn(value: str, *, expected_owner: str) -> str:
    if KMS_KEY_ARN_PATTERN.fullmatch(value) is None or f":{expected_owner}:" not in value:
        raise ValueError("KMS key must be an exact key ARN owned by the archive account")
    return value


def require_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"AWS response must contain {label}")
    return value


def require_datetime(value: object, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"AWS response must contain timezone-aware {label}")
    return value.astimezone(UTC)


def read_clock(clock: Callable[[], datetime], *, label: str) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} clock value must be timezone-aware")
    return value.astimezone(UTC)


def validate_temporary_identity(sts: StsClient, *, expected_owner: str) -> str:
    identity = sts.get_caller_identity()
    if set(identity) - {"UserId", "Account", "Arn", "ResponseMetadata"}:
        raise ValueError("STS identity response contains unexpected fields")
    account = identity.get("Account")
    arn = identity.get("Arn")
    if (
        account != expected_owner
        or not isinstance(arn, str)
        or not arn.startswith(f"arn:aws:sts::{expected_owner}:assumed-role/")
        or len(arn) > 512
    ):
        raise ValueError("archive writer must use an assumed role in the archive account")
    return arn


def validate_head_response(
    response: dict[str, Any],
    *,
    version_id: str,
    checksum_base64: str,
    size_bytes: int,
    retain_until: datetime,
    kms_key_arn: str,
) -> datetime:
    retained_until = require_datetime(
        response.get("ObjectLockRetainUntilDate"), label="ObjectLockRetainUntilDate"
    )
    if (
        response.get("VersionId") != version_id
        or response.get("ChecksumSHA256") != checksum_base64
        or response.get("ChecksumType") != "FULL_OBJECT"
        or response.get("ContentLength") != size_bytes
        or response.get("ContentType") != CONTENT_TYPE
        or response.get("ObjectLockMode") != "COMPLIANCE"
        or retained_until < retain_until
        or response.get("ServerSideEncryption") != "aws:kms"
        or response.get("SSEKMSKeyId") != kms_key_arn
        or response.get("BucketKeyEnabled") is not True
    ):
        raise ValueError("S3 object metadata does not satisfy the immutable archive contract")
    return retained_until


def read_back_sha256(body: ReadableBody) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := body.read(1024 * 1024):
            if not isinstance(chunk, bytes):
                raise ValueError("S3 read-back body must yield bytes")
            size += len(chunk)
            if size > MAX_READ_BACK_BYTES:
                raise ValueError("S3 read-back exceeds the maximum archive size")
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest(), size


def export_archive_to_s3(
    *,
    s3: S3Client,
    sts: StsClient,
    archive_path: Path,
    local_receipt_path: Path,
    bucket: str,
    expected_bucket_owner: str,
    kms_key_arn: str,
    retain_until: datetime,
    output_directory: Path,
    clock: Callable[[], datetime] | None = None,
) -> ProviderUploadEvidence:
    if archive_path.name != ARCHIVE_NAME or local_receipt_path.name != RECEIPT_NAME:
        raise ValueError("archive and local receipt must use the fixed transfer filenames")
    bucket = validate_bucket_name(bucket)
    expected_bucket_owner = validate_expected_owner(expected_bucket_owner)
    kms_key_arn = validate_kms_key_arn(kms_key_arn, expected_owner=expected_bucket_owner)
    if retain_until.tzinfo is None or retain_until.utcoffset() is None:
        raise ValueError("retain_until must be timezone-aware")
    retain_until = retain_until.astimezone(UTC)
    now = clock or (lambda: datetime.now(UTC))
    if retain_until <= read_clock(now, label="preflight"):
        raise ValueError("retain_until must be in the future")

    provider_evidence_path = output_directory / PROVIDER_EVIDENCE_NAME
    export_receipt_path = output_directory / EXPORT_RECEIPT_NAME
    if provider_evidence_path.exists() or export_receipt_path.exists():
        raise ValueError("S3 export evidence already exists; replacement is forbidden")

    output_directory.mkdir(parents=True, exist_ok=True)
    local_receipt = validate_receipt(
        read_json_object(local_receipt_path, label="local archive receipt"),
        archive_path=archive_path,
    )
    with tempfile.TemporaryDirectory(prefix=".atep-s3-preflight-", dir=output_directory) as root:
        restore_archive(
            archive_path=archive_path,
            receipt_path=local_receipt_path,
            output_directory=Path(root) / "restored",
        )

    writer_identity = validate_temporary_identity(sts, expected_owner=expected_bucket_owner)
    common = {
        "Bucket": bucket,
        "Key": local_receipt.archive_object_key,
        "ExpectedBucketOwner": expected_bucket_owner,
    }
    try:
        history = s3.list_object_versions(
            Bucket=bucket,
            Prefix=local_receipt.archive_object_key,
            MaxKeys=1,
            ExpectedBucketOwner=expected_bucket_owner,
        )
    except Exception as error:
        raise ValueError("S3 existing-key history preflight failed closed") from error
    historical_items = [
        item
        for collection in (history.get("Versions"), history.get("DeleteMarkers"))
        if isinstance(collection, list)
        for item in collection
        if isinstance(item, dict)
    ]
    if any(item.get("Key") == local_receipt.archive_object_key for item in historical_items):
        raise ValueError("S3 object key already exists; replacement is forbidden")

    checksum_base64 = base64.b64encode(bytes.fromhex(local_receipt.archive_sha256)).decode("ascii")
    try:
        with archive_path.open("rb") as archive:
            put_response = s3.put_object(
                **common,
                Body=archive,
                ContentLength=local_receipt.archive_size_bytes,
                ContentType=CONTENT_TYPE,
                ChecksumAlgorithm="SHA256",
                ChecksumSHA256=checksum_base64,
                IfNoneMatch="*",
                ObjectLockMode="COMPLIANCE",
                ObjectLockRetainUntilDate=retain_until,
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=kms_key_arn,
                BucketKeyEnabled=True,
            )
    except Exception as error:
        raise ValueError("atomic S3 archive upload failed closed") from error
    uploaded_at = read_clock(now, label="upload")
    version_id = require_string(put_response.get("VersionId"), label="VersionId")
    response_metadata = put_response.get("ResponseMetadata")
    if not isinstance(response_metadata, dict):
        raise ValueError("AWS response must contain ResponseMetadata")
    request_id = require_string(response_metadata.get("RequestId"), label="RequestId")
    if put_response.get("ChecksumSHA256") != checksum_base64:
        raise ValueError("S3 upload checksum does not match the sealed archive")

    versioned = {**common, "VersionId": version_id, "ChecksumMode": "ENABLED"}
    retained_until = validate_head_response(
        s3.head_object(**versioned),
        version_id=version_id,
        checksum_base64=checksum_base64,
        size_bytes=local_receipt.archive_size_bytes,
        retain_until=retain_until,
        kms_key_arn=kms_key_arn,
    )
    get_response = s3.get_object(**versioned)
    body = get_response.get("Body")
    if body is None or not hasattr(body, "read") or not hasattr(body, "close"):
        raise ValueError("S3 read-back response does not contain a streaming body")
    read_back_checksum, read_back_size = read_back_sha256(body)
    read_back_at = read_clock(now, label="read-back")
    if (
        get_response.get("VersionId") != version_id
        or get_response.get("ChecksumSHA256") != checksum_base64
        or get_response.get("ChecksumType") != "FULL_OBJECT"
        or get_response.get("ContentLength") != local_receipt.archive_size_bytes
        or read_back_checksum != local_receipt.archive_sha256
        or read_back_size != local_receipt.archive_size_bytes
    ):
        raise ValueError("S3 versioned read-back does not match the sealed archive")

    evidence = ProviderUploadEvidence(
        provider=AWS_PROVIDER,
        storage_resource=f"arn:aws:s3:::{bucket}",
        object_key=local_receipt.archive_object_key,
        object_version=version_id,
        checksum_sha256=local_receipt.archive_sha256,
        size_bytes=local_receipt.archive_size_bytes,
        retention_mode="locked",
        immutable_until=format_utc_timestamp(retained_until, label="immutable_until"),
        encryption_mode="customer-managed",
        writer_identity=writer_identity,
        audit_event_id=f"aws-s3-request/{request_id}",
        uploaded_at=format_utc_timestamp(uploaded_at, label="uploaded_at"),
        read_back_sha256=read_back_checksum,
        read_back_at=format_utc_timestamp(read_back_at, label="read_back_at"),
    )
    provider_value = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "status": "uploaded",
        "checksum_algorithm": "sha256",
        **asdict(evidence),
    }
    atomic_write(
        provider_evidence_path, json.dumps(provider_value, indent=2, sort_keys=True) + "\n"
    )
    build_export_receipt(
        archive_path=archive_path,
        local_receipt_path=local_receipt_path,
        provider_evidence_path=provider_evidence_path,
        output_path=export_receipt_path,
        minimum_retention_until=retain_until,
        validated_at=read_back_at,
    )
    return evidence


def create_aws_clients(*, region: str) -> tuple[S3Client, StsClient]:
    try:
        boto3 = importlib.import_module("boto3")
    except ImportError as error:
        raise RuntimeError("boto3 is required for the AWS archive exporter") from error
    session = boto3.session.Session(region_name=region)
    return session.client("s3"), session.client("sts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a sealed ATEP archive to AWS S3 Object Lock."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--local-receipt", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--expected-bucket-owner", required=True)
    parser.add_argument("--kms-key-arn", required=True)
    parser.add_argument("--retain-until", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    retain_until = parse_utc_timestamp(args.retain_until, label="retain_until")
    s3, sts = create_aws_clients(region=args.region)
    export_archive_to_s3(
        s3=s3,
        sts=sts,
        archive_path=args.archive.resolve(),
        local_receipt_path=args.local_receipt.resolve(),
        bucket=args.bucket,
        expected_bucket_owner=args.expected_bucket_owner,
        kms_key_arn=args.kms_key_arn,
        retain_until=retain_until,
        output_directory=args.output_directory.resolve(),
    )


if __name__ == "__main__":
    main()
