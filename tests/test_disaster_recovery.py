import json
from pathlib import Path
from typing import cast

import pytest

from tools.run_postgres_restore_drill import (
    DockerPostgres,
    counts_fingerprint,
    database_evidence,
    normalized_lines,
    run_drill,
    safe_compose_name,
    safe_identifier,
    sha256_file,
    table_counts,
)


class EvidencePostgres:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def psql(self, _: str, statement: str) -> str:
        for key, response in self.responses.items():
            if key in statement:
                return response
        raise AssertionError(f"unexpected statement: {statement}")


class DrillPostgres:
    def __init__(self, *, mismatch_restore: bool = False) -> None:
        self.mismatch_restore = mismatch_restore
        self.cleaned: list[tuple[str, str]] = []

    def psql(self, database: str, statement: str) -> str:
        if "version_num" in statement:
            return "0013_digital_vehicle_state\n"
        if "tablename" in statement:
            return "roles\nusers\n"
        if "information_schema.columns" in statement:
            return "roles|1|id|uuid|NO|\nusers|1|id|uuid|NO|\n"
        if '"roles"' in statement:
            return "2\n"
        if '"users"' in statement:
            return "4\n" if self.mismatch_restore and database != "atep" else "3\n"
        raise AssertionError(f"unexpected statement: {statement}")

    def create_backup(self, _: str, __: str) -> None:
        pass

    def validate_archive(self, _: str) -> None:
        pass

    def copy_from_postgres(self, _: str, local_archive: Path) -> None:
        local_archive.write_bytes(b"portable-custom-archive")

    def create_database(self, _: str) -> None:
        pass

    def restore(self, _: str, __: str) -> None:
        pass

    def cleanup(self, database: str, remote_archive: str) -> None:
        self.cleaned.append((database, remote_archive))


def postgres(responses: dict[str, str]) -> DockerPostgres:
    return cast(DockerPostgres, EvidencePostgres(responses))


def test_safe_identifier_and_normalized_lines_reject_injection_boundaries() -> None:
    assert safe_identifier("atep_restore_123", label="database") == "atep_restore_123"
    assert normalized_lines(" first \n\n second\r\n") == ["first", "second"]

    for value in ("ATEP", "restore-db", "restore;drop", "", "1restore", "a" * 64):
        with pytest.raises(ValueError, match="PostgreSQL identifier"):
            safe_identifier(value, label="database")

    assert safe_compose_name("atep-integration", label="project") == "atep-integration"
    with pytest.raises(ValueError, match="Compose name"):
        safe_compose_name("atep;integration", label="project")


def test_database_evidence_is_ordered_and_requires_one_revision() -> None:
    target = postgres(
        {
            "version_num": "0013_digital_vehicle_state\n",
            "tablename": "audit_records\nusers\n",
            "information_schema.columns": "audit_records|1|id|uuid|NO|\nusers|1|id|uuid|NO|\n",
        }
    )
    revision, tables, schema_hash = database_evidence(target, "atep")

    assert revision == "0013_digital_vehicle_state"
    assert tables == ["audit_records", "users"]
    assert len(schema_hash) == 64

    with pytest.raises(RuntimeError, match="exactly one Alembic revision"):
        database_evidence(
            postgres(
                {
                    "version_num": "0011\n0012\n",
                    "tablename": "users\n",
                    "information_schema.columns": "users|1|id|uuid|NO|\n",
                }
            ),
            "atep",
        )


def test_table_counts_and_fingerprint_are_deterministic_and_aggregate_only() -> None:
    target = postgres({"users": "3\n", "roles": "2\n"})
    first = table_counts(target, "atep", ["users", "roles"])
    second = {"roles": 2, "users": 3}

    assert first == {"users": 3, "roles": 2}
    assert counts_fingerprint(first) == counts_fingerprint(second)
    assert len(counts_fingerprint(first)) == 64
    assert "users" not in json.dumps(
        {
            "table_count": len(first),
            "total_rows": sum(first.values()),
            "table_counts_sha256": counts_fingerprint(first),
        }
    )


def test_compose_commands_do_not_contain_database_passwords(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    target = DockerPostgres(
        compose_file=compose,
        project_name="atep-integration",
        service="postgres",
        timeout_seconds=60,
    )

    assert target.compose == [
        "docker",
        "compose",
        "-p",
        "atep-integration",
        "-f",
        str(compose.resolve()),
    ]
    assert all("password" not in item.casefold() for item in target.compose)


def test_archive_hash_is_streamed_with_exact_size(tmp_path: Path) -> None:
    archive = tmp_path / "atep.dump"
    archive.write_bytes((b"atep-backup-evidence" * 70_000) + b"tail")

    digest, size = sha256_file(archive)

    assert digest == "8b59d16d77f1a3a90b36ef0cc62d70195195abe42cdbc22548f7ad8f8d007d31"
    assert size == archive.stat().st_size


def test_ci_drill_quiesces_writers_and_retains_only_safe_report() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/integration.yml").read_text(
        encoding="utf-8"
    )
    quiesce = workflow.index("Quiesce application writers for restore evidence")
    drill = workflow.index("Exercise PostgreSQL logical backup and isolated restore")
    retain = workflow.index("Retain non-sensitive disaster-recovery evidence")

    assert quiesce < drill < retain
    assert "stop api outbox-worker" in workflow
    assert "path: dr-evidence/atep-dr-report.json" in workflow
    assert "retention-days: 14" in workflow[retain:]
    assert "dr-evidence/*.dump" not in workflow

    tool = (Path(__file__).parents[1] / "tools/run_postgres_restore_drill.py").read_text(
        encoding="utf-8"
    )
    assert "--format=custom --no-owner --no-privileges" in tool
    assert "pg_restore --exit-on-error --no-owner" in tool
    assert "template=template0" in tool


def test_restore_drill_report_is_aggregate_only_and_archive_is_removed(tmp_path: Path) -> None:
    fake = DrillPostgres()
    report_path = run_drill(
        postgres=cast(DockerPostgres, fake),
        source_database="atep",
        output_directory=tmp_path,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["table_count"] == 2
    assert report["total_rows"] == 5
    assert report["archive_bytes"] == len(b"portable-custom-archive")
    assert set(report) == {
        "schema_version",
        "status",
        "started_at",
        "completed_at",
        "duration_seconds",
        "archive_sha256",
        "archive_bytes",
        "alembic_version",
        "table_count",
        "total_rows",
        "table_counts_sha256",
        "schema_sha256",
    }
    serialized = json.dumps(report)
    assert "roles" not in serialized
    assert "users" not in serialized
    assert not list(tmp_path.glob("*.dump"))
    assert len(fake.cleaned) == 1


def test_restore_mismatch_fails_and_still_cleans_temporary_state(tmp_path: Path) -> None:
    fake = DrillPostgres(mismatch_restore=True)

    with pytest.raises(RuntimeError, match="table counts"):
        run_drill(
            postgres=cast(DockerPostgres, fake),
            source_database="atep",
            output_directory=tmp_path,
        )

    assert not (tmp_path / "atep-dr-report.json").exists()
    assert not list(tmp_path.glob("*.dump"))
    assert len(fake.cleaned) == 1
