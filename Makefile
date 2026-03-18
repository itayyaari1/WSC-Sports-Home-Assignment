.PHONY: build up down logs test lint clean

build:
	docker compose build

up:
	cp -n .env.example .env 2>/dev/null || true
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd producer && pip install -r requirements.txt -q && python -m pytest tests/ -v
	cd consumer && pip install -r requirements.txt -q && python -m pytest tests/ -v

lint:
	ruff check producer/src consumer/src

clean:
	docker compose down -v --rmi local

# Phase 2 - Infrastructure
infra-init:
	terraform -chdir=terraform init

infra-plan:
	terraform -chdir=terraform plan -var-file=environments/dev.tfvars

infra-apply:
	terraform -chdir=terraform apply -var-file=environments/dev.tfvars

infra-destroy:
	terraform -chdir=terraform destroy -var-file=environments/dev.tfvars
