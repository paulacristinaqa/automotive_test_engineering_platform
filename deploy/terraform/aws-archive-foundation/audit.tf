resource "aws_cloudtrail" "archive" {
  name                          = "atep-immutable-archive"
  s3_bucket_name                = var.audit_bucket_name
  s3_key_prefix                 = "atep/archive-account-${var.archive_account_id}"
  kms_key_id                    = var.audit_kms_key_arn
  enable_log_file_validation    = true
  enable_logging                = true
  include_global_service_events = true
  is_multi_region_trail         = true

  advanced_event_selector {
    name = "ATEP archive object data events"

    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }

    field_selector {
      field  = "resources.type"
      equals = ["AWS::S3::Object"]
    }

    field_selector {
      field       = "resources.ARN"
      starts_with = ["${local.archive_bucket_arn}/"]
    }
  }

  advanced_event_selector {
    name = "ATEP archive management events"

    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }
}
