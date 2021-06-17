provider "google" {
  project = var.project_id
  region  = var.region
}

provider "random" {}

resource "google_project_service" "build" {
  project = var.project_id
  service = "cloudbuild.googleapis.com"
}

resource "google_project_service" "firestore" {
  project = var.project_id
  service = "firestore.googleapis.com"
}

resource "google_project_service" "functions" {
  project = var.project_id
  service = "cloudfunctions.googleapis.com"
}
