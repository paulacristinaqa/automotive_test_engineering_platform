# Immutable release archive provider contract

This contract defines the provider-neutral boundary for transferring sealed ATEP release evidence
to product-lifetime storage. The repository creates and restores the archive object, but no cloud
provider is selected or provisioned by this increment.

## Transfer objects

Each release produces exactly two transfer files:

- `atep-release-evidence.zip`: a deterministic ZIP_STORED object containing the archive manifest,
  release report, CycloneDX SBOM, GitHub attestation bundle, and trusted roots;
- `release-archive-receipt.json`: a schema `1.0.0` receipt containing the archive SHA-256, size,
  entry count, source SHA, image digest, manifest SHA-256, creation time, and deterministic object
  key.

The object key is fixed as:

```text
atep/releases/<40-character-source-sha>/<64-character-image-digest>/atep-release-evidence.zip
```

The exporter must reject an existing object key. Creating a new version over the same key is not a
valid substitute for non-replacement, even when the provider retains the previous version.

## Required provider capabilities

The selected storage service shall provide all of the following:

1. write-once/read-many retention that prevents overwrite and deletion for the approved period;
2. a locked retention policy that cannot be shortened or removed by the archive writer;
3. object version or generation identity returned after upload;
4. legal/event hold support when retention duration becomes incident- or regulation-dependent;
5. server-side encryption with separately governed key administration;
6. detailed, exportable control-plane and data-access audit logs;
7. checksum validation independent of multipart ETags or provider-specific weak identifiers;
8. read-after-write retrieval for immediate restore verification;
9. lifecycle configuration that cannot expire evidence before the approved product schedule; and
10. resilience, ownership, billing, and account-continuity controls appropriate to the retention
    obligation.

AWS S3 Object Lock, Azure immutable Blob Storage, and Google Cloud Bucket Lock expose relevant
WORM or locked-retention primitives, but feature names are not proof of correct configuration.
Provider approval requires retained configuration, identity, upload, denial, audit, and restore
evidence.

## Identity and authorization

Use short-lived workload identity. The archive writer may create the deterministic object, read it
back, inspect retention state, and write an upload receipt. It must not delete objects, shorten or
bypass retention, clear holds, change encryption policy, or administer audit logs.

Use a separate read-only identity for scheduled restore exercises. Retention administrators and
legal-hold operators must be independent from release writers. Break-glass access requires an
incident record, time limit, second-person approval, alerting, and post-use review.

No cloud credential, pre-signed URL, key identifier with secret material, or provider response
containing credentials may enter the sealed ZIP, GitHub artifact, logs, or workbook.

## Upload gate

An exporter shall:

1. verify the local receipt and fully restore the sealed ZIP before upload;
2. resolve the deterministic object key and fail if it already exists;
3. upload with the approved content type, retention/hold, encryption, and metadata policy;
4. compare the provider's strong checksum or a read-back SHA-256 with the local receipt;
5. confirm the immutable-until time is not shorter than the approved retention target;
6. record only non-sensitive provider evidence: provider, bucket/container identifier, object key,
   immutable version/generation, checksum, size, retention mode/until, encryption mode, audit event
   reference, and upload time; and
7. fail the release evidence export if any check is missing, mutable, ambiguous, or inconsistent.

The provider upload receipt must itself be retained independently. An upload success message or
HTTP status without read-back integrity and retention-state evidence is insufficient.

## Restore exercise

At least quarterly, and after provider, key, retention, or archive-format changes:

1. select an exact source/image digest pair from the evidence catalogue;
2. retrieve the immutable object by version/generation into an empty workspace;
3. verify its SHA-256 and size against the upload and local receipts;
4. restore the ZIP with `tools/seal_release_archive.py restore`;
5. verify the manifest-bound files and perform the documented offline attestation verification;
6. record duration, operator/automation identity, provider version, policy state, and result; and
7. delete only the temporary restore workspace, never the retained source object.

## Negative acceptance tests

- Existing key: a second upload is rejected without creating a replacement version.
- Mutable policy: unlocked, removable, or shorten-able retention blocks provider approval.
- Weak identity: a writer with delete/bypass/admin permission blocks provider approval.
- Integrity mismatch: modified ZIP, receipt, manifest, or provider checksum fails before catalogue
  registration.
- Retention mismatch: a shorter immutable-until value fails even when upload succeeded.
- Restore isolation: a non-empty destination, unsafe ZIP path, duplicate/extra entry, compressed
  entry, oversized entry, or partial extraction fails closed.
- Authorization: the restore identity cannot write; the writer cannot delete or alter retention;
  neither identity can administer audit logs or encryption keys.

## References

- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Azure immutable Blob Storage](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview)
- [Google Cloud Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock)
