from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.build_promotion_evidence import (
    IMAGE_REPOSITORY,
    validate_image_digest,
    validate_source_sha,
)
from tools.build_release_evidence import atomic_write

REPORT_SCHEMA_VERSION = "1.0.0"
SIGNER_WORKFLOW = (
    "paulacristinaqa/automotive_test_engineering_platform/"
    ".github/workflows/reusable-release-builder.yml"
)


@dataclass(frozen=True)
class ArchivedFile:
    role: str
    name: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ReleaseArchiveManifest:
    schema_version: str
    status: str
    source_sha: str
    source_ref: str
    image_digest: str
    image_reference: str
    signer_workflow: str
    offline_verification_required: bool
    created_at: str
    files: list[ArchivedFile]


def read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain one JSON object")
    return value


def validate_jsonl(path: Path, *, label: str) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be valid UTF-8 JSONL") from error
    if not values or any(not isinstance(value, dict) for value in values):
        raise ValueError(f"{label} must contain at least one JSON object")


def file_evidence(path: Path, *, role: str) -> ArchivedFile:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{role} must be a regular file")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if size == 0:
        raise ValueError(f"{role} must not be empty")
    return ArchivedFile(role=role, name=path.name, sha256=digest.hexdigest(), size_bytes=size)


def build_archive_manifest(
    *,
    source_sha: str,
    image_digest: str,
    release_evidence_path: Path,
    sbom_path: Path,
    attestation_bundle_path: Path,
    trusted_root_path: Path,
    created_at: datetime | None = None,
) -> ReleaseArchiveManifest:
    source_sha = validate_source_sha(source_sha)
    image_digest = validate_image_digest(image_digest)
    image_reference = f"{IMAGE_REPOSITORY}@{image_digest}"

    expected_bundle_names = {
        f"sha256:{image_digest.removeprefix('sha256:')}.jsonl",
        f"sha256-{image_digest.removeprefix('sha256:')}.jsonl",
    }
    archive_inputs = (
        (release_evidence_path, "release-evidence"),
        (sbom_path, "cyclonedx-sbom"),
        (attestation_bundle_path, "github-attestation-bundle"),
        (trusted_root_path, "sigstore-trusted-root"),
    )
    if (
        release_evidence_path.name != "release-evidence.json"
        or sbom_path.name != "atep-release-image.cdx.json"
        or attestation_bundle_path.name not in expected_bundle_names
        or trusted_root_path.name != "trusted_root.jsonl"
        or len({path.resolve() for path, _role in archive_inputs}) != len(archive_inputs)
    ):
        raise ValueError("archive inputs must use the fixed distinct evidence filenames")
    for path, role in archive_inputs:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{role} must be a regular file")

    release_evidence = read_json_object(release_evidence_path, label="release evidence")
    if (
        release_evidence.get("schema_version") != "1.0.0"
        or release_evidence.get("status") != "attested"
        or release_evidence.get("source_sha") != source_sha
        or release_evidence.get("image_digest") != image_digest
        or release_evidence.get("image_reference") != image_reference
        or release_evidence.get("image_name") != IMAGE_REPOSITORY
        or release_evidence.get("source_ref") != "refs/heads/main"
    ):
        raise ValueError("release evidence does not match the requested source and image")
    sbom = read_json_object(sbom_path, label="SBOM")
    if sbom.get("bomFormat") != "CycloneDX":
        raise ValueError("SBOM must be a CycloneDX document")
    validate_jsonl(attestation_bundle_path, label="attestation bundle")
    validate_jsonl(trusted_root_path, label="trusted root")

    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")

    files = [
        file_evidence(release_evidence_path, role="release-evidence"),
        file_evidence(sbom_path, role="cyclonedx-sbom"),
        file_evidence(attestation_bundle_path, role="github-attestation-bundle"),
        file_evidence(trusted_root_path, role="sigstore-trusted-root"),
    ]
    return ReleaseArchiveManifest(
        schema_version=REPORT_SCHEMA_VERSION,
        status="offline-verifiable",
        source_sha=source_sha,
        source_ref="refs/heads/main",
        image_digest=image_digest,
        image_reference=image_reference,
        signer_workflow=SIGNER_WORKFLOW,
        offline_verification_required=True,
        created_at=timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        files=files,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the ATEP release archive manifest.")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--release-evidence", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--attestation-bundle", type=Path, required=True)
    parser.add_argument("--trusted-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_archive_manifest(
        source_sha=args.source_sha,
        image_digest=args.image_digest,
        release_evidence_path=args.release_evidence.resolve(),
        sbom_path=args.sbom.resolve(),
        attestation_bundle_path=args.attestation_bundle.resolve(),
        trusted_root_path=args.trusted_root.resolve(),
    )
    atomic_write(
        args.output.resolve(),
        json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n",
    )


if __name__ == "__main__":
    main()
