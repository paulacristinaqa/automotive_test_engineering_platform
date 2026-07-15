# ATEP administrative audit retention policy

**Owner:** ATEP Core Platform Engineering  
**Effective baseline:** 15 July 2026  
**Review cadence:** At least annually and before every production deployment  
**Status:** Approved engineering baseline; archive and purge automation is not yet implemented

## Purpose and scope

This policy governs security-relevant administrative audit records stored in the ATEP Core
Platform. It covers creation, access, export, online retention, future archival, legal hold,
and eventual disposition. It does not make compliance or certification claims; customer,
contractual, regulatory, incident-response, and jurisdictional requirements may extend the
periods defined here.

## Retention classes

| Stage | Minimum period | Control |
|---|---:|---|
| Online evidence | 365 days from `created_at` | Searchable in PostgreSQL through permission-protected, bounded APIs |
| Archived evidence | Seven years from `created_at` | Encrypted, access-controlled, integrity-checked immutable object storage |
| Legal or investigation hold | Until formally released | Overrides every scheduled archive or disposition action |

The current implementation retains records indefinitely in PostgreSQL because archive and
purge automation has not yet been approved. This is conservative and protects evidence, but
capacity growth must be monitored before production use.

## Access and export

- `audit:read` permits bounded search and individual record inspection.
- `audit:export` permits CSV export independently of read access.
- Every export is capped at 10,000 rows, uses the same filters as search, and appends an
  `audit.records.exported` record with actor, correlation ID, filters, range, and row count.
- CSV output is transport evidence, not the authoritative archive. Formula-like cells are
  neutralized to reduce spreadsheet injection risk.
- Credentials, token material, password hashes, and secrets must never enter audit details.

## Immutability and disposition

The public API exposes no update or delete operation for audit records. PostgreSQL rejects
row updates and deletes through a database trigger. A future archival workflow must:

1. select a closed time partition outside the online period;
2. write encrypted records and metadata to immutable storage;
3. calculate and retain cryptographic integrity manifests;
4. verify record count, schema version, and manifest before changing online storage;
5. confirm that no legal hold applies;
6. require an approved operator change and retained execution evidence;
7. preserve an indexed catalogue that locates archived evidence.

No purge mechanism is authorized by the current implementation. Introducing one requires a
new architecture decision, threat review, restore test, migration plan, and two-person
approval procedure appropriate to the deployment environment.

## Operational evidence and review

Quarterly reviews should measure row growth, oldest/newest timestamps, query latency,
export volume, failed authorization attempts, and projected storage exhaustion. Annual
policy review must confirm retention periods, archive restorability, encryption/key
management, legal-hold ownership, and applicable external obligations.
