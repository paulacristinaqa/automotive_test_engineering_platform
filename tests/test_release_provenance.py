import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from tools.build_promotion_evidence import IMAGE_REPOSITORY, ZERO_DIGEST
from tools.build_release_evidence import (
    build_release_evidence,
    read_image_digest,
    validate_attestation_url,
)

ROOT = Path(__file__).parents[1]
VALID_DIGEST = "sha256:" + ("c" * 64)
VALID_SOURCE_SHA = "d" * 40
PROVENANCE_URL = (
    "https://github.com/paulacristinaqa/automotive_test_engineering_platform/attestations/123"
)
SBOM_URL = (
    "https://github.com/paulacristinaqa/automotive_test_engineering_platform/attestations/456"
)
SIGNER_WORKFLOW = ".github/workflows/reusable-release-builder.yml"


def test_buildx_metadata_requires_one_non_zero_sha256_digest(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"containerimage.digest": VALID_DIGEST}), encoding="utf-8")
    assert read_image_digest(metadata) == VALID_DIGEST

    for value in (ZERO_DIGEST, "latest", 42, None):
        metadata.write_text(json.dumps({"containerimage.digest": value}), encoding="utf-8")
        with pytest.raises(ValueError, match="digest"):
            read_image_digest(metadata)
    metadata.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="metadata"):
        read_image_digest(metadata)
    metadata.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="metadata"):
        read_image_digest(metadata)


def test_attestation_urls_are_exact_repository_https_urls() -> None:
    assert validate_attestation_url(PROVENANCE_URL) == PROVENANCE_URL
    for invalid in (
        "http://github.com/paulacristinaqa/automotive_test_engineering_platform/attestations/1",
        "https://github.com/other/repository/attestations/1",
        PROVENANCE_URL + "?token=secret",
        PROVENANCE_URL + "/extra",
        "not-a-url",
    ):
        with pytest.raises(ValueError, match="attestation URL"):
            validate_attestation_url(invalid)


def test_release_evidence_binds_commit_image_and_attestations() -> None:
    evidence = build_release_evidence(
        source_sha=VALID_SOURCE_SHA,
        image_digest=VALID_DIGEST,
        provenance_url=PROVENANCE_URL,
        sbom_attestation_url=SBOM_URL,
        created_at=datetime(2026, 8, 11, 16, 0, tzinfo=UTC),
    )

    assert evidence.schema_version == "1.0.0"
    assert evidence.status == "attested"
    assert evidence.source_sha == VALID_SOURCE_SHA
    assert evidence.source_ref == "refs/heads/main"
    assert evidence.image_name == IMAGE_REPOSITORY
    assert evidence.image_tag == f"sha-{VALID_SOURCE_SHA}"
    assert evidence.image_reference == f"{IMAGE_REPOSITORY}@{VALID_DIGEST}"
    assert evidence.provenance_attestation_url == PROVENANCE_URL
    assert evidence.sbom_attestation_url == SBOM_URL
    assert evidence.created_at == "2026-08-11T16:00:00Z"

    with pytest.raises(ValueError, match="timezone-aware"):
        build_release_evidence(
            source_sha=VALID_SOURCE_SHA,
            image_digest=VALID_DIGEST,
            provenance_url=PROVENANCE_URL,
            sbom_attestation_url=SBOM_URL,
            created_at=datetime(2026, 8, 11, 16, 0),
        )


def test_release_workflow_is_protected_immutable_and_least_privilege() -> None:
    caller = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    builder = (ROOT / ".github" / "workflows" / "reusable-release-builder.yml").read_text(
        encoding="utf-8"
    )
    caller_jobs = yaml.safe_load(caller)["jobs"]
    builder_jobs = yaml.safe_load(builder)["jobs"]

    assert "environment: release" in caller
    assert "ATEP_RELEASE_ENABLED: ${{ vars.ATEP_RELEASE_ENABLED }}" in caller
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in caller
    assert "uses: ./.github/workflows/reusable-release-builder.yml" in caller
    assert "needs: approve-release" in caller
    assert "packages: write" in caller
    assert "id-token: write" in caller
    assert "attestations: write" in caller
    assert "contents: write" not in caller
    assert caller_jobs["approve-release"]["permissions"] == {"contents": "read"}
    assert caller_jobs["publish-attested-image"]["permissions"] == {
        "contents": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
    }

    assert "workflow_call:" in builder
    assert "inputs:" not in builder
    assert "secrets:" not in builder
    assert "${{ job.workflow_ref }}" in builder
    assert (
        'test "$BUILDER_WORKFLOW_REF" = "$GITHUB_REPOSITORY/.github/workflows/'
        'reusable-release-builder.yml@refs/heads/main"' in builder
    )
    assert 'test "$GITHUB_REF" = "refs/heads/main"' in builder
    assert "packages: write" in builder
    assert "id-token: write" in builder
    assert "attestations: write" in builder
    assert "contents: write" not in builder
    assert builder_jobs["build-publish-attest"]["runs-on"] == "ubuntu-latest"
    assert "sha-$GITHUB_SHA" in builder
    assert "refusing replacement" in builder
    assert "--provenance=false" in builder
    assert builder.count("actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6") == 2
    assert builder.count("push-to-registry: true") == 2
    assert builder.count("create-storage-record: false") == 2


def test_promotion_requires_exact_signed_provenance_before_development() -> None:
    workflow = (ROOT / ".github" / "workflows" / "promotion.yml").read_text(encoding="utf-8")

    assert "attestations: read" in workflow
    assert "packages: read" in workflow
    assert "gh attestation verify" in workflow
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/'
        'reusable-release-builder.yml"' in workflow
    )
    assert '--source-digest "$SOURCE_SHA"' in workflow
    assert "--source-ref refs/heads/main" in workflow
    assert "--deny-self-hosted-runners" in workflow
    assert workflow.index("gh attestation verify") < workflow.index("environment: development")


def test_promotion_and_admission_trust_the_reusable_attestation_signer() -> None:
    promotion = (ROOT / ".github" / "workflows" / "promotion.yml").read_text(encoding="utf-8")
    values = (
        ROOT / "deploy" / "kubernetes" / "admission" / "github-attestation-policy-values.yaml"
    ).read_text(encoding="utf-8")
    builder = (ROOT / SIGNER_WORKFLOW).read_text(encoding="utf-8")

    assert f"$GITHUB_REPOSITORY/{SIGNER_WORKFLOW}" in promotion
    assert "workflows/reusable-release-builder[.]yml@refs/heads/main$" in values
    assert "actions/attest@" in builder
    assert "actions/attest@" not in (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
