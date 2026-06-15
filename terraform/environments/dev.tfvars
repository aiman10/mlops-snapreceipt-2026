environment = "dev"
aws_region  = "eu-west-1"

s3_buckets = [
    {
        key  = "mlops-course-dev-new-bucket"
        tags = {} 
    }
]

ecr_repositories = [
    {
        key  = "mlops-course-ehb-repository"
        image_tag_mutability = "MUTABLE"
        image_scanning_configuration = {
                scan_on_push = true
            }
        tags = {}
    }
]

apprunner_services = [
    {
        key  = "mlops-course-app"
        source_configuration = {
            image_repository = {
                image_identifier = "863745572691.dkr.ecr.eu-west-1.amazonaws.com/dev-mlops-course-ehb-repository:latest"
                image_repository_type = "ECR"
                image_configuration = {
                    port = 80
                }
            }

            autodeployments_enabled = true
        }
        tags = {}
    }
]