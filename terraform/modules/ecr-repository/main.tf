resource "aws_ecr_repository" "ecr" {
  name                 = local.name
  image_tag_mutability = var.image_tag_mutability

  image_scanning_configuration {
    scan_on_push = var.image_scanning_configuration.scan_on_push
  }

  tags = var.tags
}
