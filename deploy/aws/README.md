# AWS deployment

This is deliberately **not applied** (no live infra, no cost) — it exists to show the
target architecture and the actual Terraform for it, reviewable without an AWS bill.

## Architecture

```
Internet
   │
   ▼
Application Load Balancer  (not included below — see note)
   │
   ▼
ECS Fargate service "ledger-api" (awsvpc networking, autoscaled by CPU/RPS)
   │                                  │
   ▼                                  ▼
RDS Postgres (db.t4g.micro,     ElastiCache Redis (cache.t4g.micro)
 IAM-managed master password)    - transfers.completed stream
   │
   ▼
A second Fargate service "ledger-worker" runs `python -m app.worker`,
consuming the same Redis stream as a consumer group, independently
scalable from the API.
```

## Files

- `main.tf` — VPC (default), RDS Postgres, ElastiCache Redis, ECS cluster/task/service,
  IAM execution role, CloudWatch log group. Uses `manage_master_user_password = true`
  so the DB credential lives in Secrets Manager, not in Terraform state or env vars.
- The container image is expected to already exist in ECR (`var.container_image`) —
  built and pushed by the CI pipeline (`.github/workflows/ci.yml` would gain a
  `docker build && docker push` job on `main`).

## Deliberately out of scope here (would be added for a real production rollout)

- An Application Load Balancer + ACM cert + Route53 record in front of the ECS service.
- A second `aws_ecs_service` for the worker, and its own task definition
  (`command = ["python", "-m", "app.worker"]`).
- Multi-AZ RDS and a private-subnet-only VPC instead of the default VPC.
- `terraform plan` in CI against a real AWS account, gated by manual approval to apply.

## How to actually deploy (if you had an AWS account for it)

```bash
cd deploy/aws
terraform init
terraform plan -var="container_image=<account>.dkr.ecr.eu-north-1.amazonaws.com/ledger-api:latest"
terraform apply
```
