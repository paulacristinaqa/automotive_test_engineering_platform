resource "aws_kms_key" "archive" {
  description             = "ATEP immutable release archive"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  rotation_period_in_days = 365
  multi_region            = false

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableAccountIAMPolicies"
        Effect    = "Allow"
        Principal = { AWS = local.account_root_arn }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "SeparatedKeyAdministration"
        Effect    = "Allow"
        Principal = { AWS = sort(tolist(var.kms_administrator_role_arns)) }
        Action = [
          "kms:CancelKeyDeletion",
          "kms:DescribeKey",
          "kms:DisableKey",
          "kms:EnableKey",
          "kms:EnableKeyRotation",
          "kms:GetKeyPolicy",
          "kms:GetKeyRotationStatus",
          "kms:ListResourceTags",
          "kms:PutKeyPolicy",
          "kms:ScheduleKeyDeletion",
          "kms:TagResource",
          "kms:UntagResource",
          "kms:UpdateKeyDescription"
        ]
        Resource = "*"
      }
    ]
  })

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "archive" {
  name          = "alias/atep-release-archive"
  target_key_id = aws_kms_key.archive.key_id
}

resource "aws_s3_bucket" "archive" {
  bucket              = var.archive_bucket_name
  force_destroy       = false
  object_lock_enabled = true

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "archive" {
  bucket = aws_s3_bucket.archive.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "archive" {
  bucket = aws_s3_bucket.archive.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "archive" {
  bucket = aws_s3_bucket.archive.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "archive" {
  bucket = aws_s3_bucket.archive.id

  rule {
    bucket_key_enabled = true

    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.archive.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_object_lock_configuration" "archive" {
  bucket = aws_s3_bucket.archive.id

  depends_on = [aws_s3_bucket_versioning.archive]

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.default_retention_days
    }
  }
}

resource "aws_s3_bucket_policy" "archive" {
  bucket = aws_s3_bucket.archive.id

  depends_on = [aws_s3_bucket_public_access_block.archive]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [local.archive_bucket_arn, "${local.archive_bucket_arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "DenyOldTLS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [local.archive_bucket_arn, "${local.archive_bucket_arn}/*"]
        Condition = { NumericLessThan = { "s3:TlsVersion" = "1.2" } }
      },
      {
        Sid         = "DenyObjectsOutsideFixedPrefix"
        Effect      = "Deny"
        Principal   = "*"
        Action      = "s3:PutObject"
        NotResource = "${local.archive_bucket_arn}/${local.archive_prefix}*"
      },
      {
        Sid       = "DenyMissingOrWrongEncryption"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${local.archive_bucket_arn}/${local.archive_prefix}*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "aws:kms"
          }
        }
      },
      {
        Sid       = "DenyWrongKMSKey"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${local.archive_bucket_arn}/${local.archive_prefix}*"
        Condition = {
          ArnNotEqualsIfExists = {
            "s3:x-amz-server-side-encryption-aws-kms-key-id" = aws_kms_key.archive.arn
          }
        }
      },
      {
        Sid       = "DenyNonComplianceRetention"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObjectRetention"
        Resource  = "${local.archive_bucket_arn}/${local.archive_prefix}*"
        Condition = {
          StringNotEquals = {
            "s3:object-lock-mode" = "COMPLIANCE"
          }
        }
      },
      {
        Sid       = "DenyRetentionBelowMinimum"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObjectRetention"
        Resource  = "${local.archive_bucket_arn}/${local.archive_prefix}*"
        Condition = {
          NumericLessThan = {
            "s3:object-lock-remaining-retention-days" = tostring(var.default_retention_days)
          }
        }
      }
    ]
  })
}
