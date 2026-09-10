terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "aws_region" {
  default = "eu-north-1" # Stockholm
}

variable "container_image" {
  description = "ECR image URI for the ledger-api image, e.g. <account>.dkr.ecr.eu-north-1.amazonaws.com/ledger-api:latest"
  type        = string
}

provider "aws" {
  region = var.aws_region
}

# --- Networking: reuse the default VPC for a portfolio-scale deployment ---
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# --- Data layer ---
resource "aws_db_subnet_group" "ledger" {
  name       = "ledger-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_security_group" "rds" {
  name   = "ledger-rds-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_service.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "ledger" {
  identifier             = "ledger-db"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  db_name                = "ledger"
  username               = "ledger"
  manage_master_user_password = true
  db_subnet_group_name   = aws_db_subnet_group.ledger.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "ledger-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  subnet_group_name    = aws_elasticache_subnet_group.ledger.name
  security_group_ids   = [aws_security_group.redis.id]
}

resource "aws_elasticache_subnet_group" "ledger" {
  name       = "ledger-redis-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_security_group" "redis" {
  name   = "ledger-redis-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_service.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Compute: ECS Fargate ---
resource "aws_ecs_cluster" "ledger" {
  name = "ledger-cluster"
}

resource "aws_security_group" "ecs_service" {
  name   = "ledger-ecs-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # tighten to an ALB security group in a real deployment
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "ledger-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([
    {
      name      = "ledger-api"
      image     = var.container_image
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "REDIS_URL", value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0" }
      ]
      secrets = [
        { name = "DATABASE_URL", valueFrom = aws_db_instance.ledger.master_user_secret[0].secret_arn }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ledger-api"
        }
      }
    }
  ])
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/ledger-api"
  retention_in_days = 14
}

resource "aws_iam_role" "ecs_execution" {
  name = "ledger-ecs-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_service" "api" {
  name            = "ledger-api"
  cluster         = aws_ecs_cluster.ledger.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_service.id]
    assign_public_ip = true
  }
}
