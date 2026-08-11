output "archive_bucket_name" {
  description = "Bucket passed to tools/export_archive_to_s3.py."
  value       = aws_s3_bucket.archive.id
}

output "archive_bucket_arn" {
  description = "Immutable archive resource boundary."
  value       = aws_s3_bucket.archive.arn
}

output "archive_kms_key_arn" {
  description = "Exact customer-managed key passed to the exporter."
  value       = aws_kms_key.archive.arn
}

output "writer_role_arn" {
  description = "Short-lived role assumed by the approved archive workflow."
  value       = aws_iam_role.writer.arn
}

output "restore_role_arn" {
  description = "Read-only role used by the independently approved restore workflow."
  value       = aws_iam_role.restore.arn
}

output "cloudtrail_arn" {
  description = "Trail that records archive management and S3 object data events."
  value       = aws_cloudtrail.archive.arn
}

output "default_retention_days" {
  description = "Minimum COMPLIANCE retention enforced by this foundation."
  value       = var.default_retention_days
}
