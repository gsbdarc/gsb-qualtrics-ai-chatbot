terraform {
  backend "gcs" {
    # Bucket name provided via -backend-config during terraform init
    # Set the TF_STATE_BUCKET variable in GitHub Actions
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "gcp_services" {
  for_each = toset(var.gcp_service_list)
  project  = var.project_id
  service  = each.key
  disable_on_destroy = false
}

# 1. Create a Bucket to store the Source Code (Zipped)
resource "google_storage_bucket" "source_bucket" {
  name                        = "${var.project_id}-function-source"
  location                    = var.region
  uniform_bucket_level_access = true
}

# 2. Zip the "app" folder dynamically
data "archive_file" "source_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../app"
  output_path = "/tmp/function-source.zip"
}

# 3. Upload the Zip to the Bucket
resource "google_storage_bucket_object" "zip_object" {
  name   = "source-${data.archive_file.source_zip.output_md5}.zip"
  bucket = google_storage_bucket.source_bucket.name
  source = data.archive_file.source_zip.output_path
}

# 4. Create Firestore Database
resource "google_project_service" "firestore" {
  project = var.project_id
  service = "firestore.googleapis.com"
  
  # Prevents Terraform from disabling the API if you remove this block later
  disable_on_destroy = false
}

resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = var.firestore_db_name
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  # Wait for API to be enabled before creating DB
  depends_on = [google_project_service.firestore]
}

# 4. The Cloud Function (2nd Gen)
resource "google_cloudfunctions2_function" "default" {
  name        = "stanford-proxy-v2"
  location    = var.region
  description = "Proxy for Stanford AI API"

  build_config {
    runtime     = "python310"
    entry_point = "stanford_proxy"  # MUST match your python def
    source {
      storage_source {
        bucket = google_storage_bucket.source_bucket.name
        object = google_storage_bucket_object.zip_object.name
      }
    }
  }

  service_config {
    max_instance_count = 50
    available_memory   = "512M"
    available_cpu      = "1"
    timeout_seconds    = 300
    max_instance_request_concurrency = 80

    # Environment Variables
    environment_variables = {
      STANFORD_API_KEY           = var.stanford_api_key
      ENDPOINT_KEY               = var.endpoint_key
      PROJECT_ID                 = var.project_id
      ENABLE_LOGGING             = "false"
      SERVICE_ENABLED            = "true"
      ENDPOINT_KEY_ENABLED       = "false"
      ORIGIN_CHECK_ENABLED       = "true"
      IP_LIMITING_ENABLED        = "true"
      IP_RATE_LIMIT              = var.ip_rate_limit
      IP_MAX_RATE_LIMIT_ERRORS   = var.ip_max_rate_limit_errors
      IP_MAX_CALLS               = var.ip_max_calls
      FIRESTORE_DB_NAME          = var.firestore_db_name
      ALLOWED_ORIGINS            = var.allowed_origins
    }
  }

  # FIX 1: Wait for APIs before creating the function
  depends_on = [google_project_service.gcp_services]
}

# 5. Make it Public (Allow Unauthenticated)
resource "google_cloud_run_service_iam_member" "public_access" {
  location = google_cloudfunctions2_function.default.location
  service  = google_cloudfunctions2_function.default.name
  role     = "roles/run.invoker"
  member   = "allUsers"

  # FIX 2: THIS IS CRITICAL
  # We must tell Terraform: "Do not even LOOK at this IAM policy until 
  # the Function is created AND the APIs are fully enabled."
  depends_on = [
    google_cloudfunctions2_function.default,
    google_project_service.gcp_services
  ]
}
