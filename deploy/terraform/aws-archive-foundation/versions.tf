terraform {
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.62.0"
    }
  }

  # Supply an independently governed backend configuration during init.
  backend "s3" {}
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.archive_account_id]

  default_tags {
    tags = merge(var.tags, {
      ManagedBy      = "Terraform"
      AtepCapability = "immutable-release-archive"
    })
  }
}
