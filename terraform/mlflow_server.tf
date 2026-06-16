module "mlflow_server" {
  source = "./modules/mlflow-server"
  count  = var.enable_mlflow_server ? 1 : 0

  name            = "mlops-snapreceipt-mlflow"
  artifact_bucket = "mlops-snapreceipt-datastore-2660"
  allowed_cidr    = var.mlflow_allowed_cidr
  tags            = {}
}

output "mlflow_tracking_uri" {
  value = var.enable_mlflow_server ? module.mlflow_server[0].tracking_uri : ""
}
