output "tracking_uri" {
  value = "http://${aws_instance.mlflow.public_dns}:5000"
}

output "public_ip" {
  value = aws_instance.mlflow.public_ip
}
