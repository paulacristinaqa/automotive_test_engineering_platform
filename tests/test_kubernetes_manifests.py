from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).parents[1]
KUBERNETES = ROOT / "deploy" / "kubernetes"
ZERO_DIGEST = "sha256:" + ("0" * 64)


def load_documents(directory: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted((KUBERNETES / directory).glob("*.yaml")):
        if path.name == "kustomization.yaml":
            continue
        documents.extend(
            document
            for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if document is not None
        )
    return documents


def documents_by_kind(directory: str, kind: str) -> list[dict[str, Any]]:
    return [document for document in load_documents(directory) if document["kind"] == kind]


def test_kustomizations_reference_existing_resources_and_require_an_image_digest() -> None:
    for directory in ("foundation", "migration", "workloads"):
        path = KUBERNETES / directory / "kustomization.yaml"
        kustomization = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert kustomization["apiVersion"] == "kustomize.config.k8s.io/v1beta1"
        assert kustomization["namespace"] == "atep"
        assert all((path.parent / resource).exists() for resource in kustomization["resources"])

    for directory in ("migration", "workloads"):
        kustomization = yaml.safe_load(
            (KUBERNETES / directory / "kustomization.yaml").read_text(encoding="utf-8")
        )
        assert kustomization["images"] == [
            {
                "name": "atep-core",
                "newName": "ghcr.io/paulacristinaqa/automotive_test_engineering_platform",
                "digest": ZERO_DIGEST,
            }
        ]


def test_foundation_is_restricted_secretless_and_default_deny() -> None:
    documents = load_documents("foundation")
    assert all(document["kind"] != "Secret" for document in documents)

    namespace = documents_by_kind("foundation", "Namespace")[0]
    labels = namespace["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"

    service_accounts = documents_by_kind("foundation", "ServiceAccount")
    assert {item["metadata"]["name"] for item in service_accounts} == {
        "atep-api",
        "atep-outbox-worker",
        "atep-migration",
    }
    assert all(item["automountServiceAccountToken"] is False for item in service_accounts)

    policies = documents_by_kind("foundation", "NetworkPolicy")
    default_deny = next(item for item in policies if item["metadata"]["name"] == "default-deny")
    assert default_deny["spec"] == {
        "podSelector": {},
        "policyTypes": ["Ingress", "Egress"],
    }

    config = documents_by_kind("foundation", "ConfigMap")[0]["data"]
    assert not any("SECRET" in key or "PASSWORD" in key for key in config)
    assert config["ATEP_ENVIRONMENT"] == "production"


def test_workloads_apply_restricted_runtime_controls_and_external_secret_contract() -> None:
    deployments = documents_by_kind("workloads", "Deployment")
    assert {item["metadata"]["name"] for item in deployments} == {
        "atep-api",
        "atep-outbox-worker",
    }

    for deployment in deployments:
        assert deployment["spec"]["replicas"] == 1
        assert deployment["spec"]["strategy"]["type"] == "Recreate"
        pod_spec = deployment["spec"]["template"]["spec"]
        assert pod_spec["automountServiceAccountToken"] is False
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
        container = pod_spec["containers"][0]
        assert container["image"] == "atep-core"
        assert container["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        }
        assert set(container["resources"]) == {"requests", "limits"}
        assert "startupProbe" in container
        assert "livenessProbe" in container
        assert container["envFrom"] == [
            {"configMapRef": {"name": "atep-runtime-config"}},
            {"secretRef": {"name": "atep-runtime-secrets"}},
        ]


def test_migration_is_a_bounded_separate_job_with_the_same_security_contract() -> None:
    jobs = documents_by_kind("migration", "Job")
    assert len(jobs) == 1
    job = jobs[0]
    assert job["metadata"]["name"] == "atep-migrate"
    assert job["spec"]["backoffLimit"] == 3
    assert job["spec"]["ttlSecondsAfterFinished"] == 86400
    pod_spec = job["spec"]["template"]["spec"]
    assert pod_spec["restartPolicy"] == "Never"
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    container = pod_spec["containers"][0]
    assert container["args"] == ["alembic", "upgrade", "head"]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]


def test_api_has_dependency_readiness_persistent_evidence_and_internal_service() -> None:
    documents = load_documents("workloads")
    api = next(
        item
        for item in documents
        if item["kind"] == "Deployment" and item["metadata"]["name"] == "atep-api"
    )
    container = api["spec"]["template"]["spec"]["containers"][0]
    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"
    assert any(
        volume.get("persistentVolumeClaim", {}).get("claimName") == "atep-artifacts"
        for volume in api["spec"]["template"]["spec"]["volumes"]
    )

    service = documents_by_kind("workloads", "Service")[0]
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["ports"] == [{"name": "http", "port": 8000, "targetPort": "http"}]
