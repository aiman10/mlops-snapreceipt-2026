variable "name" {
  description = "Name of the ECR repository"
  type        = string
}

variable "environment" {
  description = "Deployment environment"
  type        = string
}

variable "delimiter" {
  description = "Resource name delimiter"
  type        = string
  default     = "-"
}

variable "image_tag_mutability" {
  description = "Tag mutability setting: MUTABLE or IMMUTABLE"
  type        = string
  default     = "MUTABLE"
}

variable "image_scanning_configuration" {
  description = "Image scanning config object with scan_on_push bool"
  type        = object({ scan_on_push = bool })
  default     = { scan_on_push = true }
}

variable "tags" {
  description = "Map of tags to assign to the resource"
  type        = map(string)
  default     = {}
}
