from __future__ import annotations

import io
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tools.build_release_archive_manifest import build_archive_manifest
from tools.export_archive_to_s3 import (
    export_archive_to_s3,
    validate_bucket_name,
    validate_expected_owner,
    validate_kms_key_arn,
)
from tools.seal_release_archive import ARCHIVE_NAME, MANIFEST_NAME, RECEIPT_NAME, seal_archive
from tools.validate_archive_export import EXPORT_RECEIPT_NAME, PROVIDER_EVIDENCE_NAME

SOURCE_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + ("b" * 64)
BUNDLE_NAME = "sha256-" + ("b" * 64) + ".jsonl"
OWNER = "123456789012"
BUCKET = "atep-immutable-release-evidence"
KMS_KEY = f"arn:aws:kms:eu-west-1:{OWNER}:key/12345678-1234-1234-1234-1234567890ab"
RETAIN_UNTIL = datetime(2040, 8, 11, tzinfo=UTC)


class FakeAwsError(Exception):
    def __init__(self, code: str, status: int) -> None:
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": status},
        }


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self._body = io.BytesIO(content)
        self.closed = False

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def close(self) -> None:
        self.closed = True
        self._body.close()


class FakeSts:
    def __init__(self, arn: str | None = None) -> None:
        self.arn = arn or f"arn:aws:sts::{OWNER}:assumed-role/atep-archive-writer/run-001"

    def get_caller_identity(self) -> dict[str, Any]:
        return {"Account": OWNER, "Arn": self.arn, "UserId": "role-session"}


class FakeS3:
    def __init__(self) -> None:
        self.content: bytes | None = None
        self.put_args: dict[str, object] = {}
        self.version_id = "version-0000000001"
        self.request_id = "request-0000000001"
        self.override: dict[str, object] = {}
        self.read_back_content: bytes | None = None
        self.existing = False
        self.delete_marker = False
        self.put_error: Exception | None = None

    def list_object_versions(self, **kwargs: object) -> dict[str, Any]:
        key = kwargs["Prefix"]
        if self.existing:
            return {"Versions": [{"Key": key, "VersionId": "existing-version"}]}
        if self.delete_marker:
            return {"DeleteMarkers": [{"Key": key, "VersionId": "delete-marker"}]}
        return {"Versions": [], "DeleteMarkers": []}

    def head_object(self, **kwargs: object) -> dict[str, Any]:
        if self.content is None:
            raise AssertionError("head_object is only valid after upload")
        response: dict[str, Any] = {
            "VersionId": self.version_id,
            "ChecksumSHA256": self.put_args["ChecksumSHA256"],
            "ChecksumType": "FULL_OBJECT",
            "ContentLength": len(self.content),
            "ContentType": "application/zip",
            "ObjectLockMode": "COMPLIANCE",
            "ObjectLockRetainUntilDate": RETAIN_UNTIL,
            "ServerSideEncryption": "aws:kms",
            "SSEKMSKeyId": KMS_KEY,
            "BucketKeyEnabled": True,
        }
        response.update(self.override)
        return response

    def put_object(self, **kwargs: object) -> dict[str, Any]:
        if self.put_error is not None:
            raise self.put_error
        self.put_args = kwargs
        body = kwargs["Body"]
        assert hasattr(body, "read")
        self.content = body.read()
        return {
            "VersionId": self.version_id,
            "ChecksumSHA256": kwargs["ChecksumSHA256"],
            "ResponseMetadata": {"RequestId": self.request_id},
        }

    def get_object(self, **kwargs: object) -> dict[str, Any]:
        assert self.content is not None
        content = self.read_back_content if self.read_back_content is not None else self.content
        return {
            "Body": FakeBody(content),
            "VersionId": self.version_id,
            "ChecksumSHA256": self.put_args["ChecksumSHA256"],
            "ChecksumType": "FULL_OBJECT",
            "ContentLength": len(self.content),
        }


def write_archive_inputs(directory: Path) -> tuple[Path, Path]:
    values = {
        "release-evidence.json": {
            "schema_version": "1.0.0",
            "status": "attested",
            "source_sha": SOURCE_SHA,
            "source_ref": "refs/heads/main",
            "image_name": "ghcr.io/paulacristinaqa/automotive_test_engineering_platform",
            "image_tag": f"sha-{SOURCE_SHA}",
            "image_digest": IMAGE_DIGEST,
            "image_reference": (
                "ghcr.io/paulacristinaqa/automotive_test_engineering_platform@" + IMAGE_DIGEST
            ),
            "provenance_attestation_url": (
                "https://github.com/paulacristinaqa/automotive_test_engineering_platform/"
                "attestations/123"
            ),
            "sbom_attestation_url": (
                "https://github.com/paulacristinaqa/automotive_test_engineering_platform/"
                "attestations/124"
            ),
            "created_at": "2026-08-11T20:30:00Z",
        },
        "atep-release-image.cdx.json": {"bomFormat": "CycloneDX"},
        BUNDLE_NAME: {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"},
        "trusted_root.jsonl": {"mediaType": "application/vnd.dev.sigstore.trustedroot+json"},
    }
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
    manifest = build_archive_manifest(
        source_sha=SOURCE_SHA,
        image_digest=IMAGE_DIGEST,
        release_evidence_path=directory / "release-evidence.json",
        sbom_path=directory / "atep-release-image.cdx.json",
        attestation_bundle_path=directory / BUNDLE_NAME,
        trusted_root_path=directory / "trusted_root.jsonl",
        created_at=datetime(2026, 8, 11, 20, 30, tzinfo=UTC),
    )
    manifest_path = directory / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(asdict(manifest), indent=2) + "\n",
        encoding="utf-8",
    )
    archive = directory / ARCHIVE_NAME
    receipt = directory / RECEIPT_NAME
    seal_archive(manifest_path=manifest_path, output_path=archive, receipt_path=receipt)
    return archive, receipt


def run_export(
    tmp_path: Path, *, s3: FakeS3 | None = None, sts: FakeSts | None = None
) -> tuple[FakeS3, Path]:
    archive, receipt = write_archive_inputs(tmp_path)
    client = s3 or FakeS3()
    output = tmp_path / "export"
    output.mkdir()
    moments = iter(
        [
            datetime(2026, 8, 11, 20, 31, tzinfo=UTC),
            datetime(2026, 8, 11, 20, 32, tzinfo=UTC),
            datetime(2026, 8, 11, 20, 33, tzinfo=UTC),
        ]
    )
    export_archive_to_s3(
        s3=client,
        sts=sts or FakeSts(),
        archive_path=archive,
        local_receipt_path=receipt,
        bucket=BUCKET,
        expected_bucket_owner=OWNER,
        kms_key_arn=KMS_KEY,
        retain_until=RETAIN_UNTIL,
        output_directory=output,
        clock=lambda: next(moments),
    )
    return client, output


def test_s3_export_uses_atomic_compliance_upload_and_versioned_readback(tmp_path: Path) -> None:
    s3, output = run_export(tmp_path)

    assert s3.put_args["IfNoneMatch"] == "*"
    assert s3.put_args["ChecksumAlgorithm"] == "SHA256"
    assert s3.put_args["ObjectLockMode"] == "COMPLIANCE"
    assert s3.put_args["ObjectLockRetainUntilDate"] == RETAIN_UNTIL
    assert s3.put_args["ServerSideEncryption"] == "aws:kms"
    assert s3.put_args["SSEKMSKeyId"] == KMS_KEY
    assert s3.put_args["BucketKeyEnabled"] is True
    provider = json.loads((output / PROVIDER_EVIDENCE_NAME).read_text(encoding="utf-8"))
    assert provider["provider"] == "aws-s3-object-lock"
    assert provider["object_version"] == s3.version_id
    assert provider["retention_mode"] == "locked"
    assert provider["writer_identity"].startswith("arn:aws:sts::")
    assert (output / EXPORT_RECEIPT_NAME).is_file()
    assert not any(path.name.startswith(".atep-s3-preflight-") for path in output.iterdir())


def test_s3_export_rejects_an_existing_key_before_upload(tmp_path: Path) -> None:
    s3 = FakeS3()
    s3.existing = True
    with pytest.raises(ValueError, match="already exists"):
        run_export(tmp_path, s3=s3)
    assert not s3.put_args


def test_s3_export_rejects_a_historical_key_hidden_by_delete_marker(tmp_path: Path) -> None:
    s3 = FakeS3()
    s3.delete_marker = True
    with pytest.raises(ValueError, match="already exists"):
        run_export(tmp_path, s3=s3)
    assert not s3.put_args


def test_s3_export_rejects_a_concurrent_conditional_upload_conflict(tmp_path: Path) -> None:
    s3 = FakeS3()
    s3.put_error = FakeAwsError("PreconditionFailed", 412)
    with pytest.raises(ValueError, match="atomic S3 archive upload failed closed"):
        run_export(tmp_path, s3=s3)


@pytest.mark.parametrize(
    ("validator", "value", "message"),
    [
        (validate_bucket_name, "Invalid_Bucket", "bucket"),
        (validate_expected_owner, "1234", "12-digit"),
        (lambda value: validate_kms_key_arn(value, expected_owner=OWNER), "alias/atep", "key ARN"),
    ],
)
def test_s3_export_rejects_ambiguous_provider_configuration(
    validator: Any, value: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validator(value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ObjectLockMode", "GOVERNANCE"),
        ("ObjectLockRetainUntilDate", datetime(2039, 8, 11, tzinfo=UTC)),
        ("ChecksumSHA256", "wrong"),
        ("VersionId", "wrong-version"),
        ("ServerSideEncryption", "AES256"),
        ("SSEKMSKeyId", "arn:aws:kms:eu-west-1:123456789012:key/wrong"),
        ("BucketKeyEnabled", False),
    ],
)
def test_s3_export_rejects_weak_or_inconsistent_object_metadata(
    tmp_path: Path, field: str, value: object
) -> None:
    s3 = FakeS3()
    s3.override[field] = value
    with pytest.raises(ValueError, match="metadata does not satisfy"):
        run_export(tmp_path, s3=s3)


def test_s3_export_rejects_tampered_versioned_readback(tmp_path: Path) -> None:
    s3 = FakeS3()
    s3.read_back_content = b"tampered"
    with pytest.raises(ValueError, match="read-back does not match"):
        run_export(tmp_path, s3=s3)


def test_s3_export_rejects_permanent_iam_user_identity(tmp_path: Path) -> None:
    sts = FakeSts(f"arn:aws:iam::{OWNER}:user/archive-writer")
    with pytest.raises(ValueError, match="must use an assumed role"):
        run_export(tmp_path, sts=sts)
