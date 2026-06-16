data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_iam_role" "mlflow" {
  name = "${var.name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "mlflow_s3" {
  name = "${var.name}-s3"
  role = aws_iam_role.mlflow.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = ["arn:aws:s3:::${var.artifact_bucket}"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["arn:aws:s3:::${var.artifact_bucket}/mlflow/*"]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "mlflow" {
  name = "${var.name}-profile"
  role = aws_iam_role.mlflow.name
}

resource "aws_security_group" "mlflow" {
  name        = "${var.name}-sg"
  description = "MLflow tracking UI access on :5000"

  ingress {
    description = "MLflow UI / API"
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

resource "aws_instance" "mlflow" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.mlflow.name
  vpc_security_group_ids = [aws_security_group.mlflow.id]

  user_data = <<-EOF
    #!/bin/bash
    set -xe
    dnf install -y python3.11 python3.11-pip
    python3.11 -m venv /opt/mlflow-venv
    /opt/mlflow-venv/bin/pip install --upgrade pip
    /opt/mlflow-venv/bin/pip install "mlflow==3.13.0" boto3
    cat >/etc/systemd/system/mlflow.service <<'UNIT'
    [Unit]
    Description=MLflow Tracking Server
    After=network-online.target
    Wants=network-online.target
    [Service]
    ExecStart=/opt/mlflow-venv/bin/mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:////opt/mlflow.db --default-artifact-root s3://${var.artifact_bucket}/mlflow
    Restart=always
    RestartSec=5
    User=root
    Environment=AWS_DEFAULT_REGION=eu-west-1
    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl daemon-reload
    systemctl enable --now mlflow
  EOF

  user_data_replace_on_change = true

  tags = merge(var.tags, { Name = var.name })
}
