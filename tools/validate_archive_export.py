from __future__ import annotations

import argparse
import json
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.build_release_evidence import atomic_write
from tools.seal_release_archive import (
    ARCHIVE_NAME,
    RECEIPT_NAME,
    SealedArchiveReceipt,
    read_json_object,
    restore_archive,
    sha256_file,
    validate_receipt,
    validate_sha256,
)

EXPORT_SCHEMA_VERSION = "1.0.0"
PROVIDER_EVIDENCE_NAME = "provider-upload-evidence.json"
EXPORT_RECEIPT_NAME = "release-archive-export-receipt.json"
MAX_IDENTIFIER_LENGTH = 512
SLUG_PATTERN = re.compile(r"[a-z][a-z0-9-]{1,63}\Z")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9._:/+=@-]+\Z")
ENCRYPTION_MODES = {"provider-managed", "customer-managed"}


@dataclass(frozen=True)
class ProviderUploadEvidence:
    provider: str
    storage_resource: str
    object_key: str
    object_version: str
    checksum_sha256: str
    size_bytes: int
    retention_mode: str
    immutable_until: str
    encryption_mode: str
    writer_identity: str
    audit_event_id: str
    uploaded_at: str
    read_back_sha256: str
    read_back_at: str


@dataclass(frozen=True)
class ArchiveExportReceipt:
    schema_version: str
    status: str
    source_sha: str
    image_digest: str
    archive_object_key: str
    archive_sha256: str
    archive_size_bytes: int
    local_receipt_sha256: str
    provider_evidence_sha256: str
    provider: str
    storage_resource: str
    object_version: str
    retention_mode: str
    immutable_until: str
    minimum_retention_until: str
    encryption_mode: str
    writer_identity: str
    audit_event_id: str
    uploaded_at: str
    read_back_at: str
    validated_at: str


def parse_utc_timestamp(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{label} must be an ISO 8601 UTC timestamp ending in Z")
    try:
        timestamp = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO 8601 UTC timestamp ending in Z") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return timestamp.astimezone(UTC)


def format_utc_timestamp(value: datetime, *, label: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def validate_identifier(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_IDENTIFIER_LENGTH
        or IDENTIFIER_PATTERN.fullmatch(value) is None
        or ".." in value
    ):
        raise ValueError(f"{label} must be a bounded non-sensitive identifier")
    return value


def validate_provider_evidence(
    value: dict[str, Any], *, local_receipt: SealedArchiveReceipt
) -> ProviderUploadEvidence:
    expected_keys = {
        "schema_version",
        "status",
        "provider",
        "storage_resource",
        "object_key",
        "object_version",
        "checksum_algorithm",
        "checksum_sha256",
        "size_bytes",
        "retention_mode",
        "immutable_until",
        "encryption_mode",
        "writer_identity",
        "audit_event_id",
        "uploaded_at",
        "read_back_sha256",
        "read_back_at",
    }
    if set(value) != expected_keys:
        raise ValueError("provider upload evidence has unexpected or missing fields")

    provider = value["provider"]
    if not isinstance(provider, str) or SLUG_PATTERN.fullmatch(provider) is None:
        raise ValueError("provider must be a canonical bounded slug")
    storage_resource = validate_identifier(value["storage_resource"], label="storage resource")
    object_key = validate_identifier(value["object_key"], label="object key")
    object_version = validate_identifier(value["object_version"], label="object version")
    checksum = validate_sha256(value["checksum_sha256"], label="provider checksum")
    read_back_checksum = validate_sha256(value["read_back_sha256"], label="read-back checksum")
    writer_identity = validate_identifier(value["writer_identity"], label="writer identity")
    audit_event_id = validate_identifier(value["audit_event_id"], label="audit event ID")
    size = value["size_bytes"]
    encryption_mode = value["encryption_mode"]
    if (
        value["schema_version"] != EXPORT_SCHEMA_VERSION
        or value["status"] != "uploaded"
        or value["checksum_algorithm"] != "sha256"
        or object_key != local_receipt.archive_object_key
        or checksum != local_receipt.archive_sha256
        or read_back_checksum != local_receipt.archive_sha256
        or type(size) is not int
        or size != local_receipt.archive_size_bytes
        or value["retention_mode"] != "locked"
        or encryption_mode not in ENCRYPTION_MODES
    ):
        raise ValueError("provider upload evidence does not match the sealed archive contract")

    immutable_until = value["immutable_until"]
    uploaded_at = value["uploaded_at"]
    read_back_at = value["read_back_at"]
    parse_utc_timestamp(immutable_until, label="immutable_until")
    upload_time = parse_utc_timestamp(uploaded_at, label="uploaded_at")
    read_back_time = parse_utc_timestamp(read_back_at, label="read_back_at")
    if read_back_time < upload_time:
        raise ValueError("read_back_at cannot precede uploaded_at")

    return ProviderUploadEvidence(
        provider=provider,
        storage_resource=storage_resource,
        object_key=object_key,
        object_version=object_version,
        checksum_sha256=checksum,
        size_bytes=size,
        retention_mode="locked",
        immutable_until=immutable_until,
        encryption_mode=encryption_mode,
        writer_identity=writer_identity,
        audit_event_id=audit_event_id,
        uploaded_at=uploaded_at,
        read_back_sha256=read_back_checksum,
        read_back_at=read_back_at,
    )


def build_export_receipt(
    *,
    archive_path: Path,
    local_receipt_path: Path,
    provider_evidence_path: Path,
    output_path: Path,
    minimum_retention_until: datetime,
    validated_at: datetime | None = None,
) -> ArchiveExportReceipt:
    if archive_path.name != ARCHIVE_NAME or local_receipt_path.name != RECEIPT_NAME:
        raise ValueError("archive and local receipt must use the fixed transfer filenames")
    if provider_evidence_path.name != PROVIDER_EVIDENCE_NAME:
        raise ValueError(f"provider evidence must be named {PROVIDER_EVIDENCE_NAME}")
    if output_path.name != EXPORT_RECEIPT_NAME:
        raise ValueError(f"export receipt must be named {EXPORT_RECEIPT_NAME}")
    if output_path.exists():
        raise ValueError("export receipt already exists; replacement is forbidden")

    local_receipt = validate_receipt(
        read_json_object(local_receipt_path, label="local archive receipt"),
        archive_path=archive_path,
    )
    provider_evidence = validate_provider_evidence(
        read_json_object(provider_evidence_path, label="provider upload evidence"),
        local_receipt=local_receipt,
    )
    minimum_retention = format_utc_timestamp(
        minimum_retention_until, label="minimum_retention_until"
    )
    if parse_utc_timestamp(
        provider_evidence.immutable_until, label="immutable_until"
    ) < parse_utc_timestamp(minimum_retention, label="minimum_retention_until"):
        raise ValueError("provider immutable retention is shorter than the approved minimum")

    validation_time = validated_at or datetime.now(UTC)
    validated_timestamp = format_utc_timestamp(validation_time, label="validated_at")
    if parse_utc_timestamp(validated_timestamp, label="validated_at") < parse_utc_timestamp(
        provider_evidence.read_back_at, label="read_back_at"
    ):
        raise ValueError("validated_at cannot precede read_back_at")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".atep-export-validate-", dir=output_path.parent
    ) as root:
        restore_archive(
            archive_path=archive_path,
            receipt_path=local_receipt_path,
            output_directory=Path(root) / "restored",
        )

    local_receipt_sha256, _ = sha256_file(local_receipt_path)
    provider_evidence_sha256, _ = sha256_file(provider_evidence_path)
    export_receipt = ArchiveExportReceipt(
        schema_version=EXPORT_SCHEMA_VERSION,
        status="export-validated",
        source_sha=local_receipt.source_sha,
        image_digest=local_receipt.image_digest,
        archive_object_key=local_receipt.archive_object_key,
        archive_sha256=local_receipt.archive_sha256,
        archive_size_bytes=local_receipt.archive_size_bytes,
        local_receipt_sha256=local_receipt_sha256,
        provider_evidence_sha256=provider_evidence_sha256,
        provider=provider_evidence.provider,
        storage_resource=provider_evidence.storage_resource,
        object_version=provider_evidence.object_version,
        retention_mode=provider_evidence.retention_mode,
        immutable_until=provider_evidence.immutable_until,
        minimum_retention_until=minimum_retention,
        encryption_mode=provider_evidence.encryption_mode,
        writer_identity=provider_evidence.writer_identity,
        audit_event_id=provider_evidence.audit_event_id,
        uploaded_at=provider_evidence.uploaded_at,
        read_back_at=provider_evidence.read_back_at,
        validated_at=validated_timestamp,
    )
    atomic_write(output_path, json.dumps(asdict(export_receipt), indent=2, sort_keys=True) + "\n")
    return export_receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate immutable-provider evidence for a sealed ATEP release archive."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--local-receipt", type=Path, required=True)
    parser.add_argument("--provider-evidence", type=Path, required=True)
    parser.add_argument("--minimum-retention-until", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    minimum_retention_until = parse_utc_timestamp(
        args.minimum_retention_until, label="minimum_retention_until"
    )
    build_export_receipt(
        archive_path=args.archive.resolve(),
        local_receipt_path=args.local_receipt.resolve(),
        provider_evidence_path=args.provider_evidence.resolve(),
        output_path=args.output.resolve(),
        minimum_retention_until=minimum_retention_until,
    )


if __name__ == "__main__":
    main()
