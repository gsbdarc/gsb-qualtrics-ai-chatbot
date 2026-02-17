output "function_url" {
  value = google_cloudfunctions2_function.default.service_config[0].uri
}