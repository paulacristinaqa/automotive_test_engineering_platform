from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from tools.build_promotion_evidence import (
    IMAGE_REPOSITORY,
    validate_image_digest,
    validate_source_sha,
)

REPORT_SCHEMA_VERSION = "1.0.0"
ATTESTATION_PATH_PREFIX = "/paulacristinaqa/automotive_test_engineering_platform/attestations/"


@dataclass(frozen=True)
class ReleaseEvidence:
    schema_version: str
    status: str
    source_sha: str
    source_ref: str
    image_name: str
    image_tag: str
    image_digest: str
    image_reference: str
    provenance_attestation_url: str
    sbom_attestation_url: str
    created_at: str


def read_image_digest(metadata_path: Path) -> str:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        value = metadata["containerimage.digest"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        message = "build metadata does not contain a valid container image digest"
        raise ValueError(message) from error
    if not isinstance(value, str):
        raise ValueError("build metadata image digest must be a string")
    return validate_image_digest(value)


def validate_attestation_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or not parsed.path.startswith(ATTESTATION_PATH_PREFIX)
        or not parsed.path.removeprefix(ATTESTATION_PATH_PREFIX).isdigit()
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("attestation URL must identify this repository on github.com")
    return value


def build_release_evidence(
    *,
    source_sha: str,
    image_digest: str,
    provenance_url: str,
    sbom_attestation_url: str,
    created_at: datetime | None = None,
) -> ReleaseEvidence:
    source_sha = validate_source_sha(source_sha)
    image_digest = validate_image_digest(image_digest)
    provenance_url = validate_attestation_url(provenance_url)
    sbom_attestation_url = validate_attestation_url(sbom_attestation_url)
    timestamp = created_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")

    return ReleaseEvidence(
        schema_version=REPORT_SCHEMA_VERSION,
        status="attested",
        source_sha=source_sha,
        source_ref="refs/heads/main",
        image_name=IMAGE_REPOSITORY,
        image_tag=f"sha-{source_sha}",
        image_digest=image_digest,
        image_reference=f"{IMAGE_REPOSITORY}@{image_digest}",
        provenance_attestation_url=provenance_url,
        sbom_attestation_url=sbom_attestation_url,
        created_at=timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    )


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build non-sensitive ATEP release evidence.")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--provenance-url", required=True)
    parser.add_argument("--sbom-attestation-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence = build_release_evidence(
        source_sha=args.source_sha,
        image_digest=args.image_digest,
        provenance_url=args.provenance_url,
        sbom_attestation_url=args.sbom_attestation_url,
    )
    content = json.dumps(asdict(evidence), indent=2, sort_keys=True) + "\n"
    atomic_write(args.output.resolve(), content)


if __name__ == "__main__":
    main()
