locals {
  archive_prefix     = "atep/releases/"
  archive_bucket_arn = "arn:aws:s3:::${var.archive_bucket_name}"
  writer_role_name   = "atep-archive-writer"
  restore_role_name  = "atep-archive-restore"
  account_root_arn   = "arn:aws:iam::${var.archive_account_id}:root"

  oidc_trust_conditions = {
    StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
    }
  }
}

check "separated_external_controls" {
  assert {
    condition     = var.audit_bucket_name != var.archive_bucket_name
    error_message = "CloudTrail audit storage must be separate from the archive bucket."
  }

  assert {
    condition = startswith(
      var.github_oidc_provider_arn,
      "arn:aws:iam::${var.archive_account_id}:oidc-provider/"
    )
    error_message = "The GitHub OIDC provider must belong to the archive account."
  }

  assert {
    condition = alltrue([
      for arn in var.kms_administrator_role_arns :
      startswith(arn, "arn:aws:iam::${var.archive_account_id}:role/")
    ])
    error_message = "Every KMS administrator role must belong to the archive account."
  }
}
