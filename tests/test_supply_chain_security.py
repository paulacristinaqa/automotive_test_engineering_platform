import re
import tomllib
from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).parents[1]
PACKAGE_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==", re.MULTILINE)
DIRECT_PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+")
ACTION_PATTERN = re.compile(r"^\s*-?\s*uses:\s+([^@\s]+)@([0-9a-f]{40})(?:\s+#.*)?$", re.MULTILINE)


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def direct_name(requirement: str) -> str:
    match = DIRECT_PACKAGE_PATTERN.match(requirement)
    assert match is not None
    return canonical_name(match.group())


def locked_names(content: str) -> set[str]:
    return {canonical_name(name) for name in PACKAGE_PATTERN.findall(content)}


def test_runtime_and_development_locks_cover_direct_dependencies_with_hashes() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    development = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
    runtime_direct = {direct_name(item) for item in project["project"]["dependencies"]}
    development_direct = {
        direct_name(item) for item in project["project"]["optional-dependencies"]["dev"]
    }

    assert runtime_direct <= locked_names(runtime)
    assert runtime_direct | development_direct <= locked_names(development)
    for content in (runtime, development):
        assert "--hash=sha256:" in content
        assert "--index-url" not in content
        assert "--trusted-host" not in content
        assert "@ http" not in content


def test_workflows_pin_every_action_to_a_full_commit_and_define_security_gates() -> None:
    workflow_files = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    workflows = "\n".join(path.read_text(encoding="utf-8") for path in workflow_files)
    uses_lines = [line for line in workflows.splitlines() if "uses:" in line]
    local_workflows = [line.strip() for line in uses_lines if "uses: ./" in line]
    external_actions = [line for line in uses_lines if "uses: ./" not in line]
    pinned_actions = ACTION_PATTERN.findall(workflows)

    assert local_workflows == ["uses: ./.github/workflows/reusable-release-builder.yml"]
    assert len(pinned_actions) == len(external_actions)
    assert "gitleaks/gitleaks-action" in workflows
    assert "github/codeql-action/init" in workflows
    assert "github/codeql-action/analyze" in workflows
    assert "anchore/sbom-action" in workflows
    assert "anchore/scan-action" in workflows
    assert "pip_audit --require-hashes" in workflows
    assert "severity-cutoff: high" in workflows
    assert "config: .grype.yaml" in workflows
    assert "persist-credentials: false" in workflows
    assert "contents: write" not in workflows


def test_image_and_update_policy_are_immutable_and_maintained() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dependabot = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    ecosystems = {entry["package-ecosystem"] for entry in dependabot["updates"]}

    assert re.search(
        r"^FROM python:3\.14\.6-alpine3\.24@sha256:[0-9a-f]{64} AS runtime$",
        dockerfile,
        flags=re.MULTILINE,
    )
    assert "pip install --no-cache-dir --require-hashes -r requirements.lock" in dockerfile
    assert "pip install --no-cache-dir --no-deps --no-build-isolation ." in dockerfile
    assert "addgroup -S atep && adduser -S -G atep -h /home/atep atep" in dockerfile
    assert "USER atep" in dockerfile
    assert ecosystems == {"pip", "github-actions", "docker", "terraform"}
    assert all(entry["schedule"]["interval"] == "weekly" for entry in dependabot["updates"])


def test_grype_exceptions_are_exact_time_bounded_and_owned() -> None:
    path = ROOT / ".grype.yaml"
    content = path.read_text(encoding="utf-8")
    configuration = yaml.safe_load(content)
    exceptions = configuration["ignore"]

    assert "Owner: ATEP maintainers" in content
    assert "Review-by: 2026-09-05" in content
    assert {entry["vulnerability"] for entry in exceptions} == {
        "CVE-2026-11940",
        "CVE-2026-15308",
        "CVE-2026-11972",
    }
    assert all(
        entry["package"] == {"name": "python", "version": "3.14.6", "type": "binary"}
        for entry in exceptions
    )
