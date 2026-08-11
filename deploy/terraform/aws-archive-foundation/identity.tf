resource "aws_iam_role" "writer" {
  name                 = local.writer_role_name
  description          = "Short-lived ATEP immutable archive writer"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "GitHubOIDCWriter"
      Effect = "Allow"
      Principal = {
        Federated = var.github_oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = merge(local.oidc_trust_conditions, {
        StringEquals = merge(local.oidc_trust_conditions.StringEquals, {
          "token.actions.githubusercontent.com:sub" = var.writer_oidc_subject
        })
      })
    }]
  })
}

resource "aws_iam_role_policy" "writer" {
  name = "atep-immutable-archive-write"
  role = aws_iam_role.writer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InspectDeterministicKeyHistory"
        Effect   = "Allow"
        Action   = ["s3:ListBucketVersions"]
        Resource = local.archive_bucket_arn
        Condition = {
          StringLike = { "s3:prefix" = ["${local.archive_prefix}*"] }
        }
      },
      {
        Sid    = "WriteAndVerifyImmutableVersion"
        Effect = "Allow"
        Action = [
          "s3:GetObjectRetention",
          "s3:GetObjectVersion",
          "s3:PutObject",
          "s3:PutObjectRetention"
        ]
        Resource = "${local.archive_bucket_arn}/${local.archive_prefix}*"
      },
      {
        Sid    = "EncryptAndVerifyArchive"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:Encrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.archive.arn
      }
    ]
  })
}

resource "aws_iam_role" "restore" {
  name                 = local.restore_role_name
  description          = "Short-lived read-only ATEP archive restore identity"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "GitHubOIDCRestore"
      Effect = "Allow"
      Principal = {
        Federated = var.github_oidc_provider_arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = merge(local.oidc_trust_conditions, {
        StringEquals = merge(local.oidc_trust_conditions.StringEquals, {
          "token.actions.githubusercontent.com:sub" = var.restore_oidc_subject
        })
      })
    }]
  })
}

resource "aws_iam_role_policy" "restore" {
  name = "atep-immutable-archive-read"
  role = aws_iam_role.restore.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadExactArchiveVersion"
        Effect   = "Allow"
        Action   = ["s3:GetObjectRetention", "s3:GetObjectVersion"]
        Resource = "${local.archive_bucket_arn}/${local.archive_prefix}*"
      },
      {
        Sid      = "DecryptArchive"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:DescribeKey"]
        Resource = aws_kms_key.archive.arn
      }
    ]
  })
}
