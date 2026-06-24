environment = "dev"
aws_region  = "eu-west-1"

s3_buckets = [
  {
    key  = "mlops-snapreceipt-datastore-2660"
    tags = {}
  },
  {
    key  = "mlops-snapreceipt-history-2660"
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

apprunner_services = [
  {
    key = "mlops-snapreceipt-app"
    source_configuration = {
      image_repository = {
        image_identifier      = "863745572691.dkr.ecr.eu-west-1.amazonaws.com/dev-mlops-snapreceipt-repository:latest"
        image_repository_type = "ECR"
        image_configuration = {
          port = 80
        }
      }
      autodeployments_enabled = true
    }
    tags = {}
  }
]

# Phase B — MLflow tracking server (firewall locked to your IP).
# MLflow has no auth, so the security group only admits your machine.
# Logging happens locally against this server; CI does not reach it.
enable_mlflow_server = true
mlflow_allowed_cidr  = "94.226.121.112/32"
