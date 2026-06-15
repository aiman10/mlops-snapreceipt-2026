locals {
  name = join(var.delimiter, [var.environment, var.name])
}
