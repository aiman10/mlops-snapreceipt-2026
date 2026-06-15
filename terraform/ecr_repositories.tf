module "ecr_repositories" {
  source = "./modules/ecr-repository"

  for_each = { for ecr in var.ecr_repositories : ecr.key => ecr }

  name                         = each.value.key
  environment                  = var.environment
  delimiter                    = var.delimiter
  image_tag_mutability         = each.value.image_tag_mutability
  image_scanning_configuration = each.value.image_scanning_configuration
  tags                         = each.value.tags
}