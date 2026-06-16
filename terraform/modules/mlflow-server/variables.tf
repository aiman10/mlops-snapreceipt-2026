variable "name" {
  type = string
}

variable "artifact_bucket" {
  type = string
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "allowed_cidr" {
  type        = string
  description = "CIDR allowed to reach the MLflow UI on :5000. Use 0.0.0.0/0 so GitHub Actions can log to it (demo); lock to <your-ip>/32 to harden (this blocks CI)."
  default     = "0.0.0.0/0"
}

variable "tags" {
  type    = map(string)
  default = {}
}
