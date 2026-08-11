# PostgreSQL backup, restore, and disaster-recovery baseline

## Status and scope

This is the initial ATEP disaster-recovery engineering baseline. It provides a repeatable logical
backup and isolated restore drill for the PostgreSQL application database. It does not claim that
a production recovery objective has been achieved. Production evidence requires the selected
provider, region topology, encryption/key controls, immutable storage, alerting, and operator
exercises.

The drill covers the PostgreSQL system of record. Redis Pub/Sub and rate-limit state are ephemeral
and are not restored. RabbitMQ carries an at-least-once projection of the PostgreSQL transactional
outbox; unpublished database rows remain authoritative after recovery. Artifact binary storage
requires its own versioned, encrypted backup and consistency procedure.

## Initial recovery objectives

| Objective | Engineering target | Current evidence |
|---|---:|---|
| Application database RPO | 24 hours | Target only; provider schedule is not configured |
| Application database RTO | 4 hours | Target only; production environment is not deployed |
| Disposable restore-drill duration | 10 minutes | Enforced by bounded CI workflow, not equivalent to production RTO |
| Restore exercise frequency | Every pull request for the disposable logical drill; quarterly for a deployed environment | CI implementation plus future operator calendar |
| Evidence retention | 14 days for non-sensitive CI reports; production records according to the approved operations policy | CI artifact configuration implemented |

RPO and RTO must be revised using business impact analysis before production approval. The targets
above provide an explicit starting point, not a regulatory or contractual commitment.

## Logical backup contract

The drill uses PostgreSQL's custom archive format with `--no-owner` and `--no-privileges`. This
makes the application database portable to an isolated database owned by the restore operator.
Credentials remain inside the PostgreSQL container environment and never appear in command-line
arguments, logs, reports, or GitHub artifacts.

The workflow performs these steps:

1. run the disposable API/integration scenario;
2. stop the API and outbox worker so comparison evidence has no concurrent application writers;
3. record the source Alembic revision, ordered public-table catalogue, schema fingerprint, and
   table counts;
4. create a custom-format `pg_dump` archive;
5. validate its table of contents with `pg_restore --list`;
6. hash the archive in 1 MiB chunks and record its exact size;
7. create a random isolated database from `template0`;
8. restore with `pg_restore --exit-on-error`;
9. compare revision, table catalogue, schema hash, and every table count;
10. delete the dump and restored database, retaining only the aggregate evidence report.

The dump itself is never uploaded by CI because it can contain password hashes, token hashes,
audit details, vehicle observations, and other protected application data.

## Evidence report

`dr-evidence/atep-dr-report.json` contains only:

- evidence schema version and `passed` status;
- UTC start/completion times and measured duration;
- archive SHA-256 and byte size;
- Alembic revision;
- total table and row counts;
- SHA-256 fingerprints of the ordered schema and per-table counts.

The report intentionally omits table names, row values, identifiers, database credentials, and
the archive. A fingerprint proves equality within the exercise; it is not a substitute for an
encrypted immutable backup object and its provider metadata.

## Production backup design

The production implementation must add all of the following before approval:

- automated encrypted backups in an account or project separated from the application runtime;
- immutable retention and deletion protection with an independently controlled key policy;
- cross-zone and, where required by business impact, cross-region copies;
- provider-native base backup and continuous WAL archiving for point-in-time recovery;
- backup failure, age, storage-capacity, and restore-test alerts with accountable ownership;
- cluster-global object handling where roles, tablespaces, or provider grants are not managed as
  infrastructure code;
- coordinated artifact-object backup and a PostgreSQL/object consistency reconciliation;
- quarterly restore exercises, annual disaster simulation, and evidence review;
- documented legal-hold interaction and an approved disposition process.

Logical dumps complement rather than replace physical/base backups and WAL archiving. A real PITR
exercise must select a timestamp, restore the base backup and WAL into an isolated environment,
verify the recovery point, run application smoke tests, and retain provider evidence.

## Failure and rollback rules

- Never restore over the only copy of a database.
- Treat dumps as executable input from the source database; restore only trusted archives.
- Verify checksum, encryption metadata, source identity, PostgreSQL compatibility, and approval
  before restoration.
- Restore first into an isolated network and prevent application writers until validation passes.
- Do not automate database downgrade as part of application rollback.
- Preserve the damaged source and relevant WAL when incident response or forensics may require it.
- If cleanup fails, treat the temporary database/archive as an operational incident; do not hide
  the successful or failed restore result.

## Verification catalogue

| ID | Test | Objective |
|---|---|---|
| DR-001 | Identifier validation | Prevent database, Compose, service, or table command injection |
| DR-002 | Custom archive creation | Produce a non-empty portable application-database backup without owners or ACLs |
| DR-003 | Archive inspection | Reject an unreadable or invalid custom archive before restore |
| DR-004 | Isolated restore | Restore into a random empty database created from `template0` |
| DR-005 | Migration equality | Prove restored Alembic revision equals the source revision |
| DR-006 | Schema equality | Prove ordered table/column metadata fingerprints match |
| DR-007 | Data-count equality | Prove every public-table row count matches without retaining the catalogue |
| DR-008 | Secret isolation | Ensure credentials and dump content are absent from commands and retained reports |
| DR-009 | Cleanup | Delete the temporary dump and restored database on success or failure |
| DR-010 | CI evidence policy | Quiesce writers and retain only the aggregate JSON report for 14 days |
| DR-011 | Point-in-time recovery | Restore provider base backup plus WAL to a selected timestamp (planned) |
| DR-012 | Application recovery smoke | Validate readiness, authentication, outbox publication, and evidence retrieval after a deployed restore (planned) |

## References

- [PostgreSQL 17 backup and restore](https://www.postgresql.org/docs/17/backup.html)
- [PostgreSQL 17 SQL dump](https://www.postgresql.org/docs/17/backup-dump.html)
- [PostgreSQL 17 pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)
- [PostgreSQL 17 continuous archiving and PITR](https://www.postgresql.org/docs/17/continuous-archiving.html)
