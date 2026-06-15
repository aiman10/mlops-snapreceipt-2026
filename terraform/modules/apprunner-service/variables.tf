variable "name" {
  description = "(Required) Base name used for the App Runner service and IAM role."
  type        = string
}

variable "image_uri" {
  description = "(Required) Full container image URI to deploy (e.g., <account>.dkr.ecr.<region>.amazonaws.com/<repo>:<tag>)."
  type        = string
}

variable "container_port" {
  description = "(Optional) TCP port the container listens on."
  type        = number
  default     = 80
}

variable "cpu" {
  description = "(Optional) CPU units for the App Runner service."
  type        = string
  default     = "1024"
}

variable "memory" {
  description = "(Optional) Memory in MB for the App Runner service."
  type        = string
  default     = "2048"
}

variable "auto_deployments_enabled" {
  description = "(Optional) Automatically deploy new images pushed to ECR."
  type        = bool
  default     = true
}

variable "tags" {
  type        = map(string)
  description = "Map of tags to attach to resources."
}
