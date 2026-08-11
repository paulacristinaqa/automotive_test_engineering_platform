from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ENVIRONMENTS = ("development", "staging", "production")
IMAGE_REPOSITORY = "ghcr.io/paulacristinaqa/automotive_test_engineering_platform"
ZERO_DIGEST = "sha256:" + ("0" * 64)
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IMAGE_PATTERN = re.compile(r"^\s*(?:-\s*)?image:\s*(\S+)\s*$", re.MULTILINE)
KIND_PATTERN = re.compile(r"^kind:\s*(\S+)\s*$", re.MULTILINE)
REPORT_SCHEMA_VERSION = "1.1.0"


@dataclass(frozen=True)
class RenderEvidence:
    target: str
    sha256: str
    resource_count: int


@dataclass(frozen=True)
class PromotionEvidence:
    schema_version: str
    status: str
    environment: str
    source_sha: str
    image_digest: str
    image_reference: str
    started_at: str
    completed_at: str
    duration_seconds: float
    renders: list[RenderEvidence]


def utc_now() -> datetime:
    return datetime.now(UTC)


def validate_environment(value: str) -> str:
    if value not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of: {', '.join(ENVIRONMENTS)}")
    return value


def validate_image_digest(value: str) -> str:
    if not DIGEST_PATTERN.fullmatch(value) or value == ZERO_DIGEST:
        raise ValueError("image digest must be a non-zero lowercase sha256 digest")
    return value


def validate_source_sha(value: str) -> str:
    if not SOURCE_SHA_PATTERN.fullmatch(value):
        raise ValueError("source SHA must contain exactly 40 lowercase hexadecimal characters")
    return value


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def promote_rendered_manifest(rendered: str, *, target: str, image_digest: str) -> str:
    if re.search(r"^kind:\s*Secret\s*$", rendered, flags=re.MULTILINE):
        raise ValueError(f"{target} render contains a literal Kubernetes Secret")

    if target == "foundation":
        if ZERO_DIGEST in rendered or IMAGE_REPOSITORY in rendered:
            raise ValueError(f"{target} render unexpectedly contains the application image")
        return rendered

    if target == "admission":
        if IMAGE_PATTERN.findall(rendered):
            raise ValueError("admission render unexpectedly contains a workload image")
        return rendered

    placeholder = f"{IMAGE_REPOSITORY}@{ZERO_DIGEST}"
    occurrence_count = rendered.count(placeholder)
    if occurrence_count == 0:
        raise ValueError(f"{target} render does not contain the reviewed image placeholder")

    promoted = rendered.replace(placeholder, f"{IMAGE_REPOSITORY}@{image_digest}")
    if ZERO_DIGEST in promoted:
        raise ValueError(f"{target} render still contains a zero image digest")

    images = IMAGE_PATTERN.findall(promoted)
    expected = f"{IMAGE_REPOSITORY}@{image_digest}"
    if not images or any(image != expected for image in images):
        raise ValueError(f"{target} render contains an unexpected image reference")
    return promoted


def render_target(repository_root: Path, target: str, *, timeout_seconds: int) -> str:
    target_path = repository_root / "deploy" / "kubernetes" / target
    result = subprocess.run(
        ["kubectl", "kustomize", str(target_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()[-2000:] or "no diagnostic output"
        raise RuntimeError(f"Kustomize render for {target} failed: {detail}")
    return result.stdout


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def build_evidence(
    *,
    repository_root: Path,
    output_directory: Path,
    environment: str,
    image_digest: str,
    source_sha: str,
    timeout_seconds: int,
) -> PromotionEvidence:
    environment = validate_environment(environment)
    image_digest = validate_image_digest(image_digest)
    source_sha = validate_source_sha(source_sha)
    if timeout_seconds < 1 or timeout_seconds > 300:
        raise ValueError("timeout seconds must be between 1 and 300")

    started = utc_now()
    start_clock = time.monotonic()
    output_directory.mkdir(parents=True, exist_ok=True)
    renders: list[RenderEvidence] = []

    for target in ("foundation", "admission", "migration", "workloads"):
        rendered = render_target(repository_root, target, timeout_seconds=timeout_seconds)
        promoted = promote_rendered_manifest(
            rendered,
            target=target,
            image_digest=image_digest,
        )
        output_path = output_directory / f"{target}.yaml"
        atomic_write(output_path, promoted)
        renders.append(
            RenderEvidence(
                target=target,
                sha256=sha256_text(promoted),
                resource_count=len(KIND_PATTERN.findall(promoted)),
            )
        )

    completed = utc_now()
    evidence = PromotionEvidence(
        schema_version=REPORT_SCHEMA_VERSION,
        status="validated",
        environment=environment,
        source_sha=source_sha,
        image_digest=image_digest,
        image_reference=f"{IMAGE_REPOSITORY}@{image_digest}",
        started_at=started.isoformat().replace("+00:00", "Z"),
        completed_at=completed.isoformat().replace("+00:00", "Z"),
        duration_seconds=round(time.monotonic() - start_clock, 3),
        renders=renders,
    )
    atomic_write(
        output_directory / "promotion-evidence.json",
        json.dumps(asdict(evidence), indent=2, sort_keys=True) + "\n",
    )
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render immutable, secret-free Kubernetes promotion evidence."
    )
    parser.add_argument("--environment", required=True, choices=ENVIRONMENTS)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_evidence(
        repository_root=args.repository_root.resolve(),
        output_directory=args.output_directory.resolve(),
        environment=args.environment,
        image_digest=args.image_digest,
        source_sha=args.source_sha,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    main()
