variable "project_id" {
  description = "Your Google Cloud Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region (e.g. us-west1)"
  type        = string
  default     = "us-west1"
}

variable "firestore_db_name" {
  description = "Name of Firestore database, if using IP_LIMITING feature"
  type        = string
  default     = "stanford-ai-proxy-db"
}

variable "ip_rate_limit" {
  description = "Minimum number of seconds allowed between calls for a specific IP address, if using IP_LIMITING feature"
  type        = number
  default     = 0.5
}

variable "ip_max_rate_limit_errors" {
  description = "Maximum number of rate limit errors allowed for a specific IP address, if using IP_LIMITING feature"
  type        = number
  default     = 10
}

variable "ip_max_calls" {
  description = "Maximum number of calls allowed for a specific IP address, if using IP_LIMITING feature"
  type        = number
  default     = 1000
}

variable "stanford_api_key" {
  description = "The Secret API Key"
  type        = string
  sensitive   = true  # Hides it from logs
}

variable "endpoint_key" {
  description = "The Secret Endpoint Key, if being used for security"
  type        = string
  sensitive   = true  # Hides it from logs
}

variable "allowed_origins" {
  description = "List of allowed origins of request call, separated by comma"
  type        = string
  default     = "https://stanfordgsb.yul1.qualtrics.com, https://stanfordgsb.qualtrics.com, https://stanford.qualtrics.com, https://stanforduniversity.qualtrics.com"
}

variable "gcp_service_list" {
  description = "The list of APIs necessary for the project"
  type        = list(string)
  default     = [
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com", 
    "cloudbuild.googleapis.com",
    "firestore.googleapis.com",
    "datastore.googleapis.com",
    "storage.googleapis.com", 
    "logging.googleapis.com",
    "pubsub.googleapis.com"
  ]
}
