variable "bucket" {
    description = "The name of the S3 bucket. Must be globally unique."
    type        = string
    default     = null
}

variable "tags" {
  type        = map(string)
  description = "Map of tags to assign to the resource. If configured with a provider default_tags configuration block present, tags with matching keys will overwrite those defined at the provider-level."
}
