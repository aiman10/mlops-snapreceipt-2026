module "s3_bucket" {
  source   = "./modules/s3-bucket"

  for_each = { for s3 in var.s3_buckets : s3.key => s3 }

  bucket = each.value.key
  tags = each.value.tags
}