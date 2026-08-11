from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools.build_promotion_evidence import (
    IMAGE_REPOSITORY,
    validate_image_digest,
    validate_source_sha,
)
from tools.build_release_archive_manifest import REPORT_SCHEMA_VERSION, SIGNER_WORKFLOW
from tools.build_release_evidence import atomic_write

SEAL_SCHEMA_VERSION = "1.0.0"
ARCHIVE_NAME = "atep-release-evidence.zip"
RECEIPT_NAME = "release-archive-receipt.json"
MANIFEST_NAME = "release-archive-manifest.json"
EXPECTED_ROLES = (
    "release-evidence",
    "cyclonedx-sbom",
    "github-attestation-bundle",
    "sigstore-trusted-root",
)
MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ManifestFile:
    role: str
    name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ValidatedManifest:
    source_sha: str
    image_digest: str
    created_at: str
    files: tuple[ManifestFile, ...]


@dataclass(frozen=True)
class SealedArchiveReceipt:
    schema_version: str
    status: str
    source_sha: str
    image_digest: str
    archive_name: str
    archive_object_key: str
    archive_sha256: str
    archive_size_bytes: int
    manifest_sha256: str
    entry_count: int
    created_at: str


def sha256_file(path: Path) -> tuple[str, int]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{path.name} must be a regular file")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value


def validate_sha256(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 value")
    return value


def validate_simple_name(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or Path(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError(f"{label} must be one safe basename")
    return value


def validate_manifest(value: dict[str, Any], *, directory: Path | None) -> ValidatedManifest:
    expected_keys = {
        "schema_version",
        "status",
        "source_sha",
        "source_ref",
        "image_digest",
        "image_reference",
        "signer_workflow",
        "offline_verification_required",
        "created_at",
        "files",
    }
    if set(value) != expected_keys:
        raise ValueError("release archive manifest has unexpected or missing fields")
    source_sha = validate_source_sha(value["source_sha"])
    image_digest = validate_image_digest(value["image_digest"])
    if (
        value["schema_version"] != REPORT_SCHEMA_VERSION
        or value["status"] != "offline-verifiable"
        or value["source_ref"] != "refs/heads/main"
        or value["image_reference"] != f"{IMAGE_REPOSITORY}@{image_digest}"
        or value["signer_workflow"] != SIGNER_WORKFLOW
        or value["offline_verification_required"] is not True
        or not isinstance(value["created_at"], str)
        or not value["created_at"].endswith("Z")
        or not isinstance(value["files"], list)
        or len(value["files"]) != len(EXPECTED_ROLES)
    ):
        raise ValueError("release archive manifest violates the fixed evidence contract")

    files: list[ManifestFile] = []
    for expected_role, item in zip(EXPECTED_ROLES, value["files"], strict=True):
        if not isinstance(item, dict) or set(item) != {"role", "name", "sha256", "size_bytes"}:
            raise ValueError("release archive file evidence has unexpected or missing fields")
        name = validate_simple_name(item["name"], label=expected_role)
        digest = validate_sha256(item["sha256"], label=expected_role)
        size = item["size_bytes"]
        if item["role"] != expected_role or type(size) is not int or size < 1:
            raise ValueError("release archive file evidence violates the fixed role contract")
        if directory is not None:
            actual_digest, actual_size = sha256_file(directory / name)
            if actual_digest != digest or actual_size != size:
                raise ValueError(f"{expected_role} does not match the archive manifest")
        files.append(ManifestFile(expected_role, name, digest, size))
    if len({item.name for item in files}) != len(files):
        raise ValueError("release archive manifest contains duplicate filenames")
    return ValidatedManifest(source_sha, image_digest, value["created_at"], tuple(files))


def archive_object_key(manifest: ValidatedManifest) -> str:
    digest = manifest.image_digest.removeprefix("sha256:")
    return f"atep/releases/{manifest.source_sha}/{digest}/{ARCHIVE_NAME}"


def write_zip_entry(archive: zipfile.ZipFile, *, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100444 << 16
    archive.writestr(info, content)


def seal_archive(
    *, manifest_path: Path, output_path: Path, receipt_path: Path
) -> SealedArchiveReceipt:
    if manifest_path.name != MANIFEST_NAME:
        raise ValueError(f"manifest must be named {MANIFEST_NAME}")
    if output_path.name != ARCHIVE_NAME or receipt_path.name != RECEIPT_NAME:
        raise ValueError("sealed archive and receipt must use the fixed filenames")
    if output_path.exists() or receipt_path.exists():
        raise ValueError("sealed archive output already exists; replacement is forbidden")

    manifest_value = read_json_object(manifest_path, label="release archive manifest")
    manifest = validate_manifest(manifest_value, directory=manifest_path.parent)
    manifest_digest, manifest_size = sha256_file(manifest_path)
    if (
        manifest_size > MAX_ENTRY_BYTES
        or any(item.size_bytes > MAX_ENTRY_BYTES for item in manifest.files)
        or manifest_size + sum(item.size_bytes for item in manifest.files) > MAX_ARCHIVE_BYTES
    ):
        raise ValueError("release archive inputs exceed the bounded seal size")
    entries = [(MANIFEST_NAME, manifest_path.read_bytes())]
    entries.extend(
        (item.name, (manifest_path.parent / item.name).read_bytes()) for item in manifest.files
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_STORED) as archive:
            for name, content in entries:
                write_zip_entry(archive, name=name, content=content)
        archive_digest, archive_size = sha256_file(temporary)
        if archive_size > MAX_ARCHIVE_BYTES:
            raise ValueError("sealed archive exceeds the maximum supported size")
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)

    receipt = SealedArchiveReceipt(
        schema_version=SEAL_SCHEMA_VERSION,
        status="sealed",
        source_sha=manifest.source_sha,
        image_digest=manifest.image_digest,
        archive_name=ARCHIVE_NAME,
        archive_object_key=archive_object_key(manifest),
        archive_sha256=archive_digest,
        archive_size_bytes=archive_size,
        manifest_sha256=manifest_digest,
        entry_count=len(entries),
        created_at=manifest.created_at,
    )
    atomic_write(receipt_path, json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n")
    return receipt


def validate_receipt(value: dict[str, Any], *, archive_path: Path) -> SealedArchiveReceipt:
    expected_keys = set(SealedArchiveReceipt.__dataclass_fields__)
    if set(value) != expected_keys:
        raise ValueError("release archive receipt has unexpected or missing fields")
    source_sha = validate_source_sha(value["source_sha"])
    image_digest = validate_image_digest(value["image_digest"])
    archive_sha256 = validate_sha256(value["archive_sha256"], label="archive")
    manifest_sha256 = validate_sha256(value["manifest_sha256"], label="manifest")
    if (
        value["schema_version"] != SEAL_SCHEMA_VERSION
        or value["status"] != "sealed"
        or value["archive_name"] != ARCHIVE_NAME
        or archive_path.name != ARCHIVE_NAME
        or value["archive_object_key"]
        != f"atep/releases/{source_sha}/{image_digest.removeprefix('sha256:')}/{ARCHIVE_NAME}"
        or type(value["archive_size_bytes"]) is not int
        or value["archive_size_bytes"] < 1
        or type(value["entry_count"]) is not int
        or value["entry_count"] != len(EXPECTED_ROLES) + 1
        or not isinstance(value["created_at"], str)
        or not value["created_at"].endswith("Z")
    ):
        raise ValueError("release archive receipt violates the fixed seal contract")
    actual_digest, actual_size = sha256_file(archive_path)
    if actual_digest != archive_sha256 or actual_size != value["archive_size_bytes"]:
        raise ValueError("sealed archive does not match its receipt")
    return SealedArchiveReceipt(
        schema_version=SEAL_SCHEMA_VERSION,
        status="sealed",
        source_sha=source_sha,
        image_digest=image_digest,
        archive_name=ARCHIVE_NAME,
        archive_object_key=value["archive_object_key"],
        archive_sha256=archive_sha256,
        archive_size_bytes=actual_size,
        manifest_sha256=manifest_sha256,
        entry_count=value["entry_count"],
        created_at=value["created_at"],
    )


def restore_archive(
    *, archive_path: Path, receipt_path: Path, output_directory: Path
) -> ValidatedManifest:
    if receipt_path.name != RECEIPT_NAME:
        raise ValueError(f"receipt must be named {RECEIPT_NAME}")
    if output_directory.exists():
        raise ValueError("restore output already exists; replacement is forbidden")
    receipt = validate_receipt(
        read_json_object(receipt_path, label="release archive receipt"),
        archive_path=archive_path,
    )

    with zipfile.ZipFile(archive_path, "r") as archive:
        entries = archive.infolist()
        names = [validate_simple_name(entry.filename, label="ZIP entry") for entry in entries]
        if (
            len(names) != len(set(names))
            or MANIFEST_NAME not in names
            or len(entries) != receipt.entry_count
            or any(entry.compress_type != zipfile.ZIP_STORED for entry in entries)
            or any(entry.file_size < 1 or entry.file_size > MAX_ENTRY_BYTES for entry in entries)
            or sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES
        ):
            raise ValueError(
                "sealed archive has unsafe, duplicate, compressed, or oversized entries"
            )
        try:
            manifest_value = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        except (KeyError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("sealed archive manifest is invalid") from error
        if not isinstance(manifest_value, dict):
            raise ValueError("sealed archive manifest must contain one JSON object")
        manifest = validate_manifest(manifest_value, directory=None)
        expected_names = [MANIFEST_NAME, *(item.name for item in manifest.files)]
        if names != expected_names:
            raise ValueError("sealed archive entries do not match the manifest")
        if (
            manifest.source_sha != receipt.source_sha
            or manifest.image_digest != receipt.image_digest
            or manifest.created_at != receipt.created_at
            or hashlib.sha256(archive.read(MANIFEST_NAME)).hexdigest() != receipt.manifest_sha256
        ):
            raise ValueError("sealed archive manifest does not match the receipt")

        temporary = output_directory.with_name(f".{output_directory.name}.tmp")
        if temporary.exists():
            raise ValueError("temporary restore output already exists")
        try:
            temporary.mkdir(parents=True)
            for entry in entries:
                destination = temporary / entry.filename
                with archive.open(entry, "r") as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
            restored = validate_manifest(
                read_json_object(temporary / MANIFEST_NAME, label="restored manifest"),
                directory=temporary,
            )
            temporary.replace(output_directory)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    return restored


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seal or restore ATEP release evidence.")
    commands = parser.add_subparsers(dest="command", required=True)
    seal = commands.add_parser("seal")
    seal.add_argument("--manifest", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    seal.add_argument("--receipt", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--receipt", type=Path, required=True)
    restore.add_argument("--output-directory", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "seal":
        seal_archive(
            manifest_path=args.manifest.resolve(),
            output_path=args.output.resolve(),
            receipt_path=args.receipt.resolve(),
        )
    else:
        restore_archive(
            archive_path=args.archive.resolve(),
            receipt_path=args.receipt.resolve(),
            output_directory=args.output_directory.resolve(),
        )


if __name__ == "__main__":
    main()
