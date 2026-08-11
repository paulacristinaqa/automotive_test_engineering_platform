mock_provider "aws" {}

variables {
  aws_region          = "eu-west-1"
  archive_account_id  = "123456789012"
  archive_bucket_name = "atep-immutable-release-evidence-example"

  default_retention_days = 3650

  github_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  writer_oidc_subject      = "repo:paulacristinaqa/automotive_test_engineering_platform:environment:archive-write"
  restore_oidc_subject     = "repo:paulacristinaqa/automotive_test_engineering_platform:environment:archive-restore"

  kms_administrator_role_arns = [
    "arn:aws:iam::123456789012:role/security/kms-archive-administrator",
  ]

  audit_bucket_name = "atep-independent-audit-example"
  audit_kms_key_arn = "arn:aws:kms:eu-west-1:210987654321:key/12345678-1234-1234-1234-1234567890ab"
}

run "secure_archive_plan" {
  command = plan

  assert {
    condition     = aws_s3_bucket.archive.object_lock_enabled
    error_message = "Object Lock must be enabled when the bucket is created."
  }

  assert {
    condition     = !aws_s3_bucket.archive.force_destroy
    error_message = "The archive bucket must never use force_destroy."
  }

  assert {
    condition     = aws_s3_bucket_versioning.archive.versioning_configuration[0].status == "Enabled"
    error_message = "Archive versioning must remain enabled."
  }

  assert {
    condition     = aws_s3_bucket_object_lock_configuration.archive.rule[0].default_retention[0].mode == "COMPLIANCE"
    error_message = "Default retention must use COMPLIANCE mode."
  }

  assert {
    condition     = aws_s3_bucket_object_lock_configuration.archive.rule[0].default_retention[0].days == 3650
    error_message = "The planned default retention must match the approved input."
  }

  assert {
    condition     = one(one(aws_s3_bucket_server_side_encryption_configuration.archive.rule).apply_server_side_encryption_by_default).sse_algorithm == "aws:kms"
    error_message = "Archive encryption must use KMS."
  }

  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.archive.rule).bucket_key_enabled
    error_message = "The S3 Bucket Key must remain enabled."
  }

  assert {
    condition     = aws_iam_role.writer.max_session_duration == 3600
    error_message = "Writer sessions must remain short lived."
  }

  assert {
    condition     = aws_iam_role.restore.max_session_duration == 3600
    error_message = "Restore sessions must remain short lived."
  }

  assert {
    condition     = aws_cloudtrail.archive.enable_log_file_validation
    error_message = "CloudTrail log file validation must remain enabled."
  }

  assert {
    condition     = aws_cloudtrail.archive.is_multi_region_trail
    error_message = "Archive audit coverage must remain multi-Region."
  }
}

run "reject_wildcard_writer_subject" {
  command = plan

  variables {
    writer_oidc_subject = "repo:paulacristinaqa/*:environment:archive-write"
  }

  expect_failures = [var.writer_oidc_subject]
}

run "reject_shared_writer_restore_subject" {
  command = plan

  variables {
    restore_oidc_subject = "repo:paulacristinaqa/automotive_test_engineering_platform:environment:archive-write"
  }

  expect_failures = [var.restore_oidc_subject]
}

run "reject_short_retention" {
  command = plan

  variables {
    default_retention_days = 30
  }

  expect_failures = [var.default_retention_days]
}

run "reject_archive_owned_audit_storage" {
  command = plan

  variables {
    audit_bucket_name = "atep-immutable-release-evidence-example"
  }

  expect_failures = [check.separated_external_controls]
}
