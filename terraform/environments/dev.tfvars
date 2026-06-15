environment = "dev"
aws_region  = "eu-west-1"

s3_buckets = [
  {
    key  = "mlops-snapreceipt-datastore-2660"
    tags = {}
  }
]

ecr_repositories = [
  {
    key                  = "mlops-snapreceipt-repository"
    image_tag_mutability = "MUTABLE"
    image_scanning_configuration = {
      scan_on_push = true
    }
    tags = {}
  }
]

apprunner_services = []
