module "apprunner_services" {
  source = "./modules/apprunner-service"

  for_each = { for svc in var.apprunner_services : svc.key => svc }

  name                     = each.value.key
  image_uri                = each.value.source_configuration.image_repository.image_identifier
  container_port           = each.value.source_configuration.image_repository.image_configuration.port
  auto_deployments_enabled = each.value.source_configuration.autodeployments_enabled
  tags                     = each.value.tags
}
