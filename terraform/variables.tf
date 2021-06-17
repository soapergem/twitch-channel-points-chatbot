locals {
  source_files = [
    "../requirements.txt",
    "../auth.py",
    "../_select.py",
    "../webhook.py",
  ]
}

data "template_file" "files" {
  count    = length(local.source_files)
  template = file(element(local.source_files, count.index))
}

variable "client_id" {
  description = "The Client ID of your Twitch app"
  type        = "string"
}

variable "client_secret" {
  description = "The Client Secret of your Twitch app"
  type        = "string"
}

variable "max_range" {
  description = "The maximum ID in the quotes database"
  default     = 109
  type        = "string"
}

variable "min_range" {
  description = "The minimum ID in the quotes database"
  default     = 1
  type        = "string"
}

variable "project_id" {
  description = "The name of your GCP project"
  type        = "string"
}

variable "region" {
  default     = "us-east4"
  description = "The region of your GCP project"
  type        = "string"
}

variable "secret_length" {
  default     = 32
  description = "Default length of EventSub signing secrets"
  type        = "number"

  validation {
    condition     = var.secret_length >= 10 && var.secret_length <= 100
    error_message = "secret_length must be between 10 and 100"
  }
}

resource "random_string" "bucket_suffix" {
  length  = 16
  special = false
}
