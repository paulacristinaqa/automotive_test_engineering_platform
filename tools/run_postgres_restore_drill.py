from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
COMPOSE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
REPORT_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class DrillReport:
    schema_version: str
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    archive_sha256: str
    archive_bytes: int
    alembic_version: str
    table_count: int
    total_rows: int
    table_counts_sha256: str
    schema_sha256: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def safe_identifier(value: str, *, label: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase PostgreSQL identifier")
    return value


def safe_compose_name(value: str, *, label: str) -> str:
    if not COMPOSE_NAME_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase Compose name")
    return value


def normalized_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def counts_fingerprint(counts: dict[str, int]) -> str:
    payload = json.dumps(counts, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(payload)


class DockerPostgres:
    def __init__(
        self,
        *,
        compose_file: Path,
        project_name: str,
        service: str,
        timeout_seconds: int,
    ) -> None:
        self.compose_file = compose_file.resolve()
        self.project_name = safe_compose_name(project_name, label="project name")
        self.service = safe_compose_name(service, label="service")
        self.timeout_seconds = timeout_seconds

    @property
    def compose(self) -> list[str]:
        return [
            "docker",
            "compose",
            "-p",
            self.project_name,
            "-f",
            str(self.compose_file),
        ]

    def run(self, arguments: Sequence[str], *, label: str) -> str:
        result = subprocess.run(
            [*self.compose, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if result.returncode != 0:
            detail = result.stderr.strip()[-2000:] or "no diagnostic output"
            raise RuntimeError(f"{label} failed: {detail}")
        return result.stdout

    def postgres_shell(self, script: str, *arguments: str, label: str) -> str:
        return self.run(
            ["exec", "-T", self.service, "sh", "-euc", script, "--", *arguments],
            label=label,
        )

    def psql(self, database: str, statement: str) -> str:
        safe_identifier(database, label="database")
        script = (
            'PGPASSWORD="$POSTGRES_PASSWORD" psql --no-psqlrc --tuples-only --no-align '
            '--set ON_ERROR_STOP=1 --username="$POSTGRES_USER" --dbname="$1" --command="$2"'
        )
        return self.postgres_shell(script, database, statement, label="PostgreSQL query")

    def create_backup(self, database: str, remote_archive: str) -> None:
        safe_identifier(database, label="database")
        script = (
            'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --username="$POSTGRES_USER" '
            '--format=custom --no-owner --no-privileges --dbname="$1" --file="$2"'
        )
        self.postgres_shell(script, database, remote_archive, label="logical backup")

    def copy_from_postgres(self, remote_archive: str, local_archive: Path) -> None:
        self.run(
            ["cp", f"{self.service}:{remote_archive}", str(local_archive)],
            label="backup archive copy",
        )

    def validate_archive(self, remote_archive: str) -> None:
        self.postgres_shell(
            'pg_restore --list "$1" >/dev/null',
            remote_archive,
            label="backup archive validation",
        )

    def create_database(self, database: str) -> None:
        safe_identifier(database, label="restore database")
        script = (
            'PGPASSWORD="$POSTGRES_PASSWORD" createdb --username="$POSTGRES_USER" '
            '--template=template0 "$1"'
        )
        self.postgres_shell(script, database, label="restore database creation")

    def restore(self, database: str, remote_archive: str) -> None:
        safe_identifier(database, label="restore database")
        script = (
            'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore --exit-on-error --no-owner '
            '--no-privileges --username="$POSTGRES_USER" --dbname="$1" "$2"'
        )
        self.postgres_shell(script, database, remote_archive, label="logical restore")

    def cleanup(self, database: str, remote_archive: str) -> None:
        safe_identifier(database, label="restore database")
        script = (
            'PGPASSWORD="$POSTGRES_PASSWORD" dropdb --if-exists --force '
            '--username="$POSTGRES_USER" "$1"; rm -f -- "$2"'
        )
        self.postgres_shell(script, database, remote_archive, label="drill cleanup")


def database_evidence(postgres: DockerPostgres, database: str) -> tuple[str, list[str], str]:
    revision_lines = normalized_lines(
        postgres.psql(database, "SELECT version_num FROM alembic_version")
    )
    if len(revision_lines) != 1:
        raise RuntimeError("database must contain exactly one Alembic revision")

    tables = normalized_lines(
        postgres.psql(
            database,
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
        )
    )
    if not tables:
        raise RuntimeError("database contains no public tables")
    for table in tables:
        safe_identifier(table, label="table")

    schema = postgres.psql(
        database,
        "SELECT table_name || '|' || ordinal_position || '|' || column_name || '|' || "
        "data_type || '|' || is_nullable || '|' || COALESCE(column_default, '') "
        "FROM information_schema.columns WHERE table_schema = 'public' "
        "ORDER BY table_name, ordinal_position",
    )
    return revision_lines[0], tables, sha256_bytes(schema.encode())


def table_counts(postgres: DockerPostgres, database: str, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        safe_identifier(table, label="table")
        lines = normalized_lines(postgres.psql(database, f'SELECT count(*) FROM "{table}"'))
        if len(lines) != 1 or not lines[0].isdigit():
            raise RuntimeError(f"invalid row count returned for table {table}")
        counts[table] = int(lines[0])
    return counts


def run_drill(
    *,
    postgres: DockerPostgres,
    source_database: str,
    output_directory: Path,
) -> Path:
    source_database = safe_identifier(source_database, label="source database")
    restore_database = safe_identifier(f"atep_restore_{uuid4().hex[:12]}", label="restore database")
    remote_archive = f"/tmp/{restore_database}.dump"
    output_directory.mkdir(parents=True, exist_ok=True)
    local_archive = output_directory / f"{restore_database}.dump"
    report_path = output_directory / "atep-dr-report.json"
    started = utc_now()
    start_clock = time.monotonic()
    active_error: Exception | None = None

    try:
        source_revision, source_tables, source_schema_hash = database_evidence(
            postgres, source_database
        )
        source_counts = table_counts(postgres, source_database, source_tables)
        postgres.create_backup(source_database, remote_archive)
        postgres.validate_archive(remote_archive)
        postgres.copy_from_postgres(remote_archive, local_archive)
        archive_sha256, archive_bytes = sha256_file(local_archive)
        if archive_bytes == 0:
            raise RuntimeError("logical backup archive is empty")

        postgres.create_database(restore_database)
        postgres.restore(restore_database, remote_archive)
        restore_revision, restore_tables, restore_schema_hash = database_evidence(
            postgres, restore_database
        )
        restore_counts = table_counts(postgres, restore_database, restore_tables)
        if restore_revision != source_revision:
            raise RuntimeError("restored Alembic revision does not match the source")
        if restore_tables != source_tables or restore_schema_hash != source_schema_hash:
            raise RuntimeError("restored schema does not match the source")
        if restore_counts != source_counts:
            raise RuntimeError("restored table counts do not match the source")

        completed = utc_now()
        report = DrillReport(
            schema_version=REPORT_SCHEMA_VERSION,
            status="passed",
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
            duration_seconds=round(time.monotonic() - start_clock, 3),
            archive_sha256=archive_sha256,
            archive_bytes=archive_bytes,
            alembic_version=source_revision,
            table_count=len(source_counts),
            total_rows=sum(source_counts.values()),
            table_counts_sha256=counts_fingerprint(source_counts),
            schema_sha256=source_schema_hash,
        )
        report_path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
        return report_path
    except Exception as exc:
        active_error = exc
        raise
    finally:
        local_archive.unlink(missing_ok=True)
        try:
            postgres.cleanup(restore_database, remote_archive)
        except Exception:
            if active_error is None:
                raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up ATEP PostgreSQL, restore it in isolation, and emit safe evidence."
    )
    parser.add_argument("--compose-file", type=Path, default=Path("compose.integration.yaml"))
    parser.add_argument("--project-name", default="atep-integration")
    parser.add_argument("--service", default="postgres")
    parser.add_argument("--source-database", default="atep")
    parser.add_argument("--output-directory", type=Path, default=Path("dr-evidence"))
    parser.add_argument("--timeout-seconds", type=int, default=300)
    arguments = parser.parse_args()
    if not 30 <= arguments.timeout_seconds <= 3600:
        parser.error("--timeout-seconds must be between 30 and 3600")
    if not arguments.compose_file.is_file():
        parser.error("--compose-file must reference an existing file")
    return arguments


def main() -> None:
    arguments = parse_args()
    postgres = DockerPostgres(
        compose_file=arguments.compose_file,
        project_name=arguments.project_name,
        service=arguments.service,
        timeout_seconds=arguments.timeout_seconds,
    )
    report_path = run_drill(
        postgres=postgres,
        source_database=arguments.source_database,
        output_directory=arguments.output_directory,
    )
    print(report_path)


if __name__ == "__main__":
    main()
