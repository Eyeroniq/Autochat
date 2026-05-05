import pulumi

config = pulumi.Config()

project_name = "rag-local"
environment = "dev"

pulumi.export("project", project_name)
pulumi.export("environment", environment)