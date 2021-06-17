resource "google_storage_bucket" "bucket" {
  name = "${var.project_id}-code-${random_string.bucket_suffix.id}"
}

# Auth function

data "archive_file" "auth" {
  type        = "zip"
  output_path = "auth.zip"

  source {
    filename = "auth.py"
    content  = data.template_file.files.1.rendered
  }

  source {
    filename = "requirements.txt"
    content  = data.template_file.files.0.rendered
  }
}

resource "google_storage_bucket_object" "auth" {
  name   = "auth.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.auth.output_path
}

resource "google_cloudfunctions_function" "auth" {
  name                = "auth"
  description         = "Auth Endpoint"
  runtime             = "python39"
  available_memory_mb = 128
  trigger_http        = true
  timeout             = 30
  entry_point         = "handler"
  ingress_settings    = "ALLOW_ALL"

  source_archive_bucket = google_storage_bucket.bucket.name
  source_archive_object = google_storage_bucket_object.auth.name

  environment_variables = {
    CLIENT_ID     = var.client_id
    CLIENT_SECRET = var.client_secret
    REDIRECT_URI  = "https://${var.region}-${var.project_id}.cloudfunctions.net/auth"
    SELECT_URI    = "https://${var.region}-${var.project_id}.cloudfunctions.net/select"
  }

  depends_on = [google_project_service.build, google_project_service.functions]
}

resource "google_cloudfunctions_function_iam_member" "public" {
  project        = var.project_id
  region         = var.region
  cloud_function = google_cloudfunctions_function.auth.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# Select function

data "archive_file" "select" {
  type        = "zip"
  output_path = "select.zip"

  source {
    filename = "select.py"
    content  = data.template_file.files.2.rendered
  }

  source {
    filename = "requirements.txt"
    content  = data.template_file.files.0.rendered
  }
}

resource "google_storage_bucket_object" "select" {
  name   = "select.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.auth.output_path
}

resource "google_cloudfunctions_function" "select" {
  name                = "auth"
  description         = "Auth Endpoint"
  runtime             = "python39"
  available_memory_mb = 128
  trigger_http        = true
  timeout             = 30
  entry_point         = "handler"
  ingress_settings    = "ALLOW_ALL"

  source_archive_bucket = google_storage_bucket.bucket.name
  source_archive_object = google_storage_bucket_object.select.name

  environment_variables = {
    CLIENT_ID     = var.client_id
    CLIENT_SECRET = var.client_secret
    REDIRECT_URI  = "https://${var.region}-${var.project_id}.cloudfunctions.net/auth"
    SECRET_LENGTH = var.secret_length
    SELECT_URI    = "https://${var.region}-${var.project_id}.cloudfunctions.net/select"
    WEBHOOK_URI   = "https://${var.region}-${var.project_id}.cloudfunctions.net/webhook"
  }

  depends_on = [google_project_service.build, google_project_service.functions]
}

resource "google_cloudfunctions_function_iam_member" "public" {
  project        = var.project_id
  region         = var.region
  cloud_function = google_cloudfunctions_function.auth.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# Webhook function

data "archive_file" "webhook" {
  type        = "zip"
  output_path = "webhook.zip"

  source {
    filename = "webhook.py"
    content  = data.template_file.files.3.rendered
  }

  source {
    filename = "requirements.txt"
    content  = data.template_file.files.0.rendered
  }
}

resource "google_storage_bucket_object" "webhook" {
  name   = "webhook.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.auth.output_path
}

resource "google_cloudfunctions_function" "webhook" {
  name                = "auth"
  description         = "Auth Endpoint"
  runtime             = "python39"
  available_memory_mb = 128
  trigger_http        = true
  timeout             = 30
  entry_point         = "handler"
  ingress_settings    = "ALLOW_ALL"

  source_archive_bucket = google_storage_bucket.bucket.name
  source_archive_object = google_storage_bucket_object.webhook.name

  environment_variables = {
    CLIENT_ID     = var.client_id
    CLIENT_SECRET = var.client_secret
    REDIRECT_URI  = "https://${var.region}-${var.project_id}.cloudfunctions.net/auth"
    MIN_RANGE     = var.min_range
    MAX_RANGE     = var.max_range
  }

  depends_on = [google_project_service.build, google_project_service.functions]
}

resource "google_cloudfunctions_function_iam_member" "public" {
  project        = var.project_id
  region         = var.region
  cloud_function = google_cloudfunctions_function.auth.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}
