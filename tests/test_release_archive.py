import json
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.build_promotion_evidence import IMAGE_REPOSITORY
from tools.build_release_archive_manifest import build_archive_manifest
from tools.seal_release_archive import (
    ARCHIVE_NAME,
    MANIFEST_NAME,
    RECEIPT_NAME,
    restore_archive,
    seal_archive,
    sha256_file,
)

VALID_SOURCE_SHA = "a" * 40
VALID_DIGEST = "sha256:" + ("b" * 64)
ROOT = Path(__file__).parents[1]


def write_archive_inputs(directory: Path) -> tuple[Path, Path, Path, Path]:
    release = directory / "release-evidence.json"
    release.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "status": "attested",
                "source_sha": VALID_SOURCE_SHA,
                "source_ref": "refs/heads/main",
                "image_name": IMAGE_REPOSITORY,
                "image_digest": VALID_DIGEST,
                "image_reference": f"{IMAGE_REPOSITORY}@{VALID_DIGEST}",
            }
        ),
        encoding="utf-8",
    )
    sbom = directory / "atep-release-image.cdx.json"
    sbom.write_text(json.dumps({"bomFormat": "CycloneDX"}), encoding="utf-8")
    bundle = directory / f"sha256-{VALID_DIGEST.removeprefix('sha256:')}.jsonl"
    bundle.write_text(json.dumps({"mediaType": "application/vnd.dev.sigstore.bundle+json"}) + "\n")
    trusted_root = directory / "trusted_root.jsonl"
    trusted_root.write_text(
        json.dumps({"mediaType": "application/vnd.dev.sigstore.trustedroot+json"}) + "\n"
    )
    return release, sbom, bundle, trusted_root


def write_archive_manifest(directory: Path) -> Path:
    release, sbom, bundle, trusted_root = write_archive_inputs(directory)
    manifest = build_archive_manifest(
        source_sha=VALID_SOURCE_SHA,
        image_digest=VALID_DIGEST,
        release_evidence_path=release,
        sbom_path=sbom,
        attestation_bundle_path=bundle,
        trusted_root_path=trusted_root,
        created_at=datetime(2026, 8, 11, 18, 0, tzinfo=UTC),
    )
    path = directory / MANIFEST_NAME
    path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_archive_manifest_binds_offline_evidence_with_file_hashes(tmp_path: Path) -> None:
    release, sbom, bundle, trusted_root = write_archive_inputs(tmp_path)
    manifest = build_archive_manifest(
        source_sha=VALID_SOURCE_SHA,
        image_digest=VALID_DIGEST,
        release_evidence_path=release,
        sbom_path=sbom,
        attestation_bundle_path=bundle,
        trusted_root_path=trusted_root,
        created_at=datetime(2026, 8, 11, 18, 0, tzinfo=UTC),
    )

    assert manifest.schema_version == "1.0.0"
    assert manifest.status == "offline-verifiable"
    assert manifest.source_sha == VALID_SOURCE_SHA
    assert manifest.image_reference == f"{IMAGE_REPOSITORY}@{VALID_DIGEST}"
    assert manifest.offline_verification_required is True
    assert manifest.created_at == "2026-08-11T18:00:00Z"
    assert [item.role for item in manifest.files] == [
        "release-evidence",
        "cyclonedx-sbom",
        "github-attestation-bundle",
        "sigstore-trusted-root",
    ]
    assert all(item.size_bytes > 0 and len(item.sha256) == 64 for item in manifest.files)
    assert asdict(manifest)["files"][2]["name"].startswith("sha256-")


def test_archive_manifest_rejects_mismatched_or_malformed_evidence(tmp_path: Path) -> None:
    release, sbom, bundle, trusted_root = write_archive_inputs(tmp_path)
    release.write_text(json.dumps({"source_sha": "c" * 40}), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        build_archive_manifest(
            source_sha=VALID_SOURCE_SHA,
            image_digest=VALID_DIGEST,
            release_evidence_path=release,
            sbom_path=sbom,
            attestation_bundle_path=bundle,
            trusted_root_path=trusted_root,
        )

    release, sbom, bundle, trusted_root = write_archive_inputs(tmp_path)
    bundle.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="attestation bundle"):
        build_archive_manifest(
            source_sha=VALID_SOURCE_SHA,
            image_digest=VALID_DIGEST,
            release_evidence_path=release,
            sbom_path=sbom,
            attestation_bundle_path=bundle,
            trusted_root_path=trusted_root,
        )


def test_archive_manifest_rejects_empty_or_naive_timestamp_inputs(tmp_path: Path) -> None:
    release, sbom, bundle, trusted_root = write_archive_inputs(tmp_path)
    trusted_root.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="trusted root"):
        build_archive_manifest(
            source_sha=VALID_SOURCE_SHA,
            image_digest=VALID_DIGEST,
            release_evidence_path=release,
            sbom_path=sbom,
            attestation_bundle_path=bundle,
            trusted_root_path=trusted_root,
        )

    _, _, bundle, trusted_root = write_archive_inputs(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_archive_manifest(
            source_sha=VALID_SOURCE_SHA,
            image_digest=VALID_DIGEST,
            release_evidence_path=release,
            sbom_path=sbom,
            attestation_bundle_path=bundle,
            trusted_root_path=trusted_root,
            created_at=datetime(2026, 8, 11, 18, 0),
        )


def test_archive_manifest_rejects_renamed_or_duplicate_inputs(tmp_path: Path) -> None:
    release, sbom, bundle, trusted_root = write_archive_inputs(tmp_path)
    renamed_bundle = tmp_path / "attestations.jsonl"
    bundle.replace(renamed_bundle)
    with pytest.raises(ValueError, match="fixed distinct"):
        build_archive_manifest(
            source_sha=VALID_SOURCE_SHA,
            image_digest=VALID_DIGEST,
            release_evidence_path=release,
            sbom_path=sbom,
            attestation_bundle_path=renamed_bundle,
            trusted_root_path=trusted_root,
        )

    release, _sbom, bundle, trusted_root = write_archive_inputs(tmp_path)
    with pytest.raises(ValueError, match="fixed distinct"):
        build_archive_manifest(
            source_sha=VALID_SOURCE_SHA,
            image_digest=VALID_DIGEST,
            release_evidence_path=release,
            sbom_path=release,
            attestation_bundle_path=bundle,
            trusted_root_path=trusted_root,
        )


def test_reusable_builder_archives_and_verifies_portable_release_evidence() -> None:
    workflow = (ROOT / ".github" / "workflows" / "reusable-release-builder.yml").read_text(
        encoding="utf-8"
    )

    assert "gh attestation download" in workflow
    assert "gh attestation trusted-root > trusted_root.jsonl" in workflow
    assert '--bundle "$BUNDLE_FILE"' in workflow
    assert "--custom-trusted-root trusted_root.jsonl" in workflow
    assert "--signer-workflow" in workflow
    assert "python tools/build_release_archive_manifest.py" in workflow
    assert "release-archive-manifest.json" in workflow
    assert "atep-release-offline-archive-${{ github.sha }}" in workflow
    assert workflow.index("Verify the archived provenance bundle") < workflow.index(
        "Retain portable offline-verification evidence"
    )


def test_sealed_archive_is_deterministic_and_restores_from_its_receipt(tmp_path: Path) -> None:
    manifest_path = write_archive_manifest(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    receipt = seal_archive(
        manifest_path=manifest_path,
        output_path=first / ARCHIVE_NAME,
        receipt_path=first / RECEIPT_NAME,
    )
    seal_archive(
        manifest_path=manifest_path,
        output_path=second / ARCHIVE_NAME,
        receipt_path=second / RECEIPT_NAME,
    )

    assert (first / ARCHIVE_NAME).read_bytes() == (second / ARCHIVE_NAME).read_bytes()
    assert (first / RECEIPT_NAME).read_bytes() == (second / RECEIPT_NAME).read_bytes()
    assert receipt.archive_object_key.endswith(f"/{ARCHIVE_NAME}")
    assert receipt.entry_count == 5

    restored = restore_archive(
        archive_path=first / ARCHIVE_NAME,
        receipt_path=first / RECEIPT_NAME,
        output_directory=tmp_path / "restored",
    )
    assert restored.source_sha == VALID_SOURCE_SHA
    assert restored.image_digest == VALID_DIGEST
    assert (tmp_path / "restored" / MANIFEST_NAME).is_file()
    assert {path.name for path in (tmp_path / "restored").iterdir()} == {
        MANIFEST_NAME,
        *(item.name for item in restored.files),
    }


def test_restore_rejects_tampering_and_existing_output(tmp_path: Path) -> None:
    manifest_path = write_archive_manifest(tmp_path)
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    archive = sealed / ARCHIVE_NAME
    receipt = sealed / RECEIPT_NAME
    seal_archive(manifest_path=manifest_path, output_path=archive, receipt_path=receipt)

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        restore_archive(archive_path=archive, receipt_path=receipt, output_directory=existing)

    content = bytearray(archive.read_bytes())
    content[-1] ^= 1
    archive.write_bytes(content)
    with pytest.raises(ValueError, match="does not match its receipt"):
        restore_archive(
            archive_path=archive,
            receipt_path=receipt,
            output_directory=tmp_path / "tampered",
        )


def test_restore_rejects_extra_or_unsafe_zip_entries(tmp_path: Path) -> None:
    manifest_path = write_archive_manifest(tmp_path)
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    archive = sealed / ARCHIVE_NAME
    receipt = sealed / RECEIPT_NAME
    seal_archive(manifest_path=manifest_path, output_path=archive, receipt_path=receipt)

    original_entries: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(archive, "r") as source:
        original_entries = [(entry.filename, source.read(entry)) for entry in source.infolist()]
    archive.unlink()
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as target:
        for name, content in original_entries:
            target.writestr(name, content, compress_type=zipfile.ZIP_STORED)
        target.writestr("../escape.txt", b"unsafe", compress_type=zipfile.ZIP_STORED)

    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    receipt_value["archive_sha256"], receipt_value["archive_size_bytes"] = sha256_file(archive)
    receipt.write_text(json.dumps(receipt_value), encoding="utf-8")
    with pytest.raises(ValueError, match="safe basename"):
        restore_archive(
            archive_path=archive,
            receipt_path=receipt,
            output_directory=tmp_path / "unsafe",
        )


def test_reusable_builder_restores_the_downloaded_sealed_archive() -> None:
    workflow = (ROOT / ".github" / "workflows" / "reusable-release-builder.yml").read_text(
        encoding="utf-8"
    )

    assert "Seal the deterministic archive object" in workflow
    assert "archive-restore-smoke:" in workflow
    assert "needs: build-publish-attest" in workflow
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow
    assert "python tools/seal_release_archive.py restore" in workflow
    assert workflow.index("Retain portable offline-verification evidence") < workflow.index(
        "archive-restore-smoke:"
    )
