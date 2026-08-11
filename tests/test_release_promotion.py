import json
from dataclasses import asdict
from pathlib import Path

import pytest

from tools.build_promotion_evidence import (
    IMAGE_REPOSITORY,
    ZERO_DIGEST,
    build_evidence,
    promote_rendered_manifest,
    validate_environment,
    validate_image_digest,
    validate_source_sha,
)

ROOT = Path(__file__).parents[1]
VALID_DIGEST = "sha256:" + ("a" * 64)
VALID_SOURCE_SHA = "b" * 40


def test_promotion_inputs_are_strict_and_fail_closed() -> None:
    assert validate_environment("production") == "production"
    assert validate_image_digest(VALID_DIGEST) == VALID_DIGEST
    assert validate_source_sha(VALID_SOURCE_SHA) == VALID_SOURCE_SHA

    for invalid in ("prod", "", "Production"):
        with pytest.raises(ValueError, match="environment"):
            validate_environment(invalid)
    for invalid in (ZERO_DIGEST, "sha256:ABC", "latest", "sha256:" + ("a" * 63)):
        with pytest.raises(ValueError, match="digest"):
            validate_image_digest(invalid)
    for invalid in ("main", "A" * 40, "b" * 39, "b" * 41):
        with pytest.raises(ValueError, match="source SHA"):
            validate_source_sha(invalid)


def test_manifest_promotion_replaces_only_the_reviewed_image_and_rejects_secrets() -> None:
    source = (
        "apiVersion: apps/v1\n"
        "kind: Deployment\n"
        "spec:\n"
        "  template:\n"
        "    spec:\n"
        "      containers:\n"
        f"        - image: {IMAGE_REPOSITORY}@{ZERO_DIGEST}\n"
    )
    promoted = promote_rendered_manifest(
        source,
        target="workloads",
        image_digest=VALID_DIGEST,
    )
    assert ZERO_DIGEST not in promoted
    assert f"image: {IMAGE_REPOSITORY}@{VALID_DIGEST}" in promoted

    with pytest.raises(ValueError, match="literal Kubernetes Secret"):
        promote_rendered_manifest(
            "apiVersion: v1\nkind: Secret\n",
            target="workloads",
            image_digest=VALID_DIGEST,
        )
    with pytest.raises(ValueError, match="reviewed image placeholder"):
        promote_rendered_manifest(
            source.replace(IMAGE_REPOSITORY, "registry.invalid/atep"),
            target="workloads",
            image_digest=VALID_DIGEST,
        )


def test_evidence_report_binds_source_digest_environment_and_render_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_render(_root: Path, target: str, *, timeout_seconds: int) -> str:
        assert timeout_seconds == 30
        if target == "foundation":
            return "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: atep\n"
        return (
            "apiVersion: batch/v1\n"
            f"kind: {'Job' if target == 'migration' else 'Deployment'}\n"
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"        - image: {IMAGE_REPOSITORY}@{ZERO_DIGEST}\n"
        )

    monkeypatch.setattr("tools.build_promotion_evidence.render_target", fake_render)
    evidence = build_evidence(
        repository_root=ROOT,
        output_directory=tmp_path,
        environment="staging",
        image_digest=VALID_DIGEST,
        source_sha=VALID_SOURCE_SHA,
        timeout_seconds=30,
    )

    report = json.loads((tmp_path / "promotion-evidence.json").read_text(encoding="utf-8"))
    assert report == asdict(evidence)
    assert report["schema_version"] == "1.0.0"
    assert report["status"] == "validated"
    assert report["environment"] == "staging"
    assert report["source_sha"] == VALID_SOURCE_SHA
    assert report["image_digest"] == VALID_DIGEST
    assert [item["target"] for item in report["renders"]] == [
        "foundation",
        "migration",
        "workloads",
    ]
    assert all(item["resource_count"] == 1 for item in report["renders"])
    assert all(len(item["sha256"]) == 64 for item in report["renders"])
    assert ZERO_DIGEST not in (tmp_path / "workloads.yaml").read_text(encoding="utf-8")


def test_promotion_workflow_has_fixed_ordered_environments_and_no_deploy_command() -> None:
    workflow = (ROOT / ".github" / "workflows" / "promotion.yml").read_text(
        encoding="utf-8"
    )

    assert "environment: development" in workflow
    assert "environment: staging" in workflow
    assert "environment: production" in workflow
    assert "needs: validate-release" in workflow
    assert "needs: development" in workflow
    assert "needs: staging" in workflow
    assert workflow.count('ATEP_PROMOTION_ENABLED: ${{ vars.ATEP_PROMOTION_ENABLED }}') == 3
    assert "kubectl apply" not in workflow
    assert "contents: write" not in workflow
    assert "id-token: write" not in workflow
