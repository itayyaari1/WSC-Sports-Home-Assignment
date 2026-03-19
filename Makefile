.PHONY: build up down logs test test-docker lint clean local-install local-infra run-producer run-consumer

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
	cd producer && pip3 install -r requirements.txt -q && PYTHONPATH=$(PWD) python3 -m pytest tests/ -v
	cd consumer && pip3 install -r requirements.txt -q && PYTHONPATH=$(PWD) python3 -m pytest tests/ -v

test-docker: build
	docker compose run --rm --no-deps producer python -m pytest tests/ -v
	docker compose run --rm --no-deps consumer python -m pytest tests/ -v

local-install:
	ln -sf $(PWD)/.env producer/.env
	ln -sf $(PWD)/.env consumer/.env
	python3 -m venv producer/.venv && producer/.venv/bin/pip install -r producer/requirements.txt
	python3 -m venv consumer/.venv && consumer/.venv/bin/pip install -r consumer/requirements.txt

local-infra:
	docker compose up zookeeper kafka minio minio-init -d

run-producer:
	cd producer && PYTHONPATH=$(PWD) .venv/bin/python -m src.main

run-consumer:
	cd consumer && PYTHONPATH=$(PWD) .venv/bin/python -m src.main

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
