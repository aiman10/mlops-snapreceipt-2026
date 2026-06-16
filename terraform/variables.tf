variable "aws_region" {
  description = "AWS region"
  default     = "eu-west-1"
}

variable "environment" {
  description = "Specifies the deployment environment of the resources (e.g., sandbox, dev, tst, acc, prd)"
  type        = string
  default     = "dev"
}

variable "delimiter" {
  description = "Resource name delimiter"
  type        = string
  default     = "-"
}

variable "s3_buckets" {
  description = "A list of S3 Buckets"
  type        = list(any)
  default     = []
}

variable "ecr_repositories" {
  description = "A list of ECR Repositories"
  type        = list(any)
  default     = []
}

variable "apprunner_services" {
  description = "A list of App Runner services"
  type        = list(any)
  default     = []
}

variable "enable_mlflow_server" {
  description = "Whether to provision the MLflow tracking server (EC2)"
  type        = bool
  default     = false
}

variable "mlflow_allowed_cidr" {
  description = "CIDR allowed to reach MLflow on :5000 (0.0.0.0/0 lets GitHub Actions log to it)"
  type        = string
  default     = "0.0.0.0/0"
}