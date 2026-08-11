variable "aws_region" {
  description = "Commercial AWS region that owns the archive bucket and KMS key."
  type        = string
  default     = "eu-west-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region must be a canonical commercial AWS region name."
  }
}

variable "archive_account_id" {
  description = "Dedicated AWS account that owns the immutable archive."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.archive_account_id))
    error_message = "archive_account_id must contain exactly 12 digits."
  }
}

variable "archive_bucket_name" {
  description = "Globally unique name for the new general-purpose Object Lock bucket."
  type        = string

  validation {
    condition = (
      length(var.archive_bucket_name) >= 3 &&
      length(var.archive_bucket_name) <= 63 &&
      can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.archive_bucket_name)) &&
      !strcontains(var.archive_bucket_name, "..") &&
      !strcontains(var.archive_bucket_name, ".-") &&
      !strcontains(var.archive_bucket_name, "-.") &&
      !can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.archive_bucket_name)) &&
      alltrue([for prefix in ["xn--", "sthree-", "amzn-s3-demo-"] : !startswith(var.archive_bucket_name, prefix)]) &&
      alltrue([for suffix in ["-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3"] : !endswith(var.archive_bucket_name, suffix)])
    )
    error_message = "archive_bucket_name must be a canonical general-purpose S3 bucket name."
  }
}

variable "default_retention_days" {
  description = "Default and minimum COMPLIANCE retention applied to every archive version."
  type        = number
  default     = 3650

  validation {
    condition = (
      var.default_retention_days == floor(var.default_retention_days) &&
      var.default_retention_days >= 365 &&
      var.default_retention_days <= 36500
    )
    error_message = "default_retention_days must be an integer between 365 and 36500."
  }
}

variable "github_oidc_provider_arn" {
  description = "ARN of the independently managed GitHub Actions OIDC provider in the archive account."
  type        = string

  validation {
    condition = can(regex(
      "^arn:aws:iam::[0-9]{12}:oidc-provider/token[.]actions[.]githubusercontent[.]com$",
      var.github_oidc_provider_arn
    ))
    error_message = "github_oidc_provider_arn must identify the official GitHub OIDC provider."
  }
}

variable "writer_oidc_subject" {
  description = "Exact approved GitHub OIDC subject for immutable archive writes. Wildcards are forbidden."
  type        = string

  validation {
    condition = (
      length(var.writer_oidc_subject) >= 20 &&
      length(var.writer_oidc_subject) <= 512 &&
      can(regex("^repo:paulacristinaqa(@[0-9]+)?/automotive_test_engineering_platform(@[0-9]+)?:", var.writer_oidc_subject)) &&
      strcontains(var.writer_oidc_subject, ":environment:") &&
      !strcontains(var.writer_oidc_subject, "*") &&
      !strcontains(var.writer_oidc_subject, "?")
    )
    error_message = "writer_oidc_subject must be one exact bounded GitHub repository subject."
  }
}

variable "restore_oidc_subject" {
  description = "Exact approved GitHub OIDC subject for clean-host archive restoration."
  type        = string

  validation {
    condition = (
      length(var.restore_oidc_subject) >= 20 &&
      length(var.restore_oidc_subject) <= 512 &&
      can(regex("^repo:paulacristinaqa(@[0-9]+)?/automotive_test_engineering_platform(@[0-9]+)?:", var.restore_oidc_subject)) &&
      strcontains(var.restore_oidc_subject, ":environment:") &&
      !strcontains(var.restore_oidc_subject, "*") &&
      !strcontains(var.restore_oidc_subject, "?") &&
      var.restore_oidc_subject != var.writer_oidc_subject
    )
    error_message = "restore_oidc_subject must be exact, bounded, and separate from the writer subject."
  }
}

variable "kms_administrator_role_arns" {
  description = "Existing archive-account roles allowed to administer, but not use, the archive KMS key."
  type        = set(string)

  validation {
    condition = (
      length(var.kms_administrator_role_arns) >= 1 &&
      alltrue([
        for arn in var.kms_administrator_role_arns :
        can(regex("^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$", arn))
      ])
    )
    error_message = "Provide at least one canonical existing IAM role ARN for KMS administration."
  }
}

variable "audit_bucket_name" {
  description = "Name of the independently governed S3 bucket that receives CloudTrail logs."
  type        = string

  validation {
    condition = (
      length(var.audit_bucket_name) >= 3 &&
      length(var.audit_bucket_name) <= 63 &&
      can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.audit_bucket_name)) &&
      !strcontains(var.audit_bucket_name, "..") &&
      !strcontains(var.audit_bucket_name, ".-") &&
      !strcontains(var.audit_bucket_name, "-.") &&
      !can(regex("^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$", var.audit_bucket_name)) &&
      alltrue([for prefix in ["xn--", "sthree-", "amzn-s3-demo-"] : !startswith(var.audit_bucket_name, prefix)]) &&
      alltrue([for suffix in ["-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3"] : !endswith(var.audit_bucket_name, suffix)])
    )
    error_message = "audit_bucket_name must be a canonical S3 bucket name."
  }
}

variable "audit_kms_key_arn" {
  description = "KMS key ARN controlled by the audit-storage owner for CloudTrail log encryption."
  type        = string

  validation {
    condition = can(regex(
      "^arn:aws:kms:[a-z]{2}-[a-z]+-[0-9]+:[0-9]{12}:key/[0-9a-fA-F-]{36}$",
      var.audit_kms_key_arn
    ))
    error_message = "audit_kms_key_arn must be an exact commercial AWS KMS key ARN."
  }
}

variable "tags" {
  description = "Ownership and cost-allocation tags merged with the module's fixed tags."
  type        = map(string)
  default = {
    Project            = "ATEP"
    Environment        = "production"
    DataClassification = "release-evidence"
  }

  validation {
    condition = alltrue([
      for required in ["Project", "Environment", "DataClassification"] :
      contains(keys(var.tags), required) && length(trimspace(var.tags[required])) > 0
    ])
    error_message = "tags must retain non-empty Project, Environment, and DataClassification values."
  }
}
