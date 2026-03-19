.PHONY: build up down logs logs-producer test test-docker lint clean local-install local-infra run-producer run-producer-docker run-consumer \
        minikube-start minikube-build minikube-dashboard helm-deps k8s-up k8s-down k8s-status k8s-run-producer k8s-logs-producer k8s-logs-consumer

build:
	docker compose build

up:
	cp -n .env.example .env 2>/dev/null || true
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=50

logs-producer:
	docker compose logs producer

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

run-producer-docker:
	docker compose up zookeeper kafka -d --wait
	docker compose run --rm producer

run-consumer:
	cd consumer && PYTHONPATH=$(PWD) .venv/bin/python -m src.main

lint:
	ruff check producer/src consumer/src

clean:
	docker compose down -v --rmi local



# ---------------------------------------------------------------------------
# Phase 2 - Kubernetes (Minikube)
# Prerequisites: minikube, helm, kubectl
# ---------------------------------------------------------------------------

# Start Minikube with enough resources for Kafka + MinIO
minikube-start:
	minikube start --cpus=4 --memory=6144

# Open the Minikube Kubernetes dashboard in the default browser
minikube-dashboard:
	minikube dashboard

# Build producer & consumer images directly inside Minikube's Docker daemon.
# imagePullPolicy: Never in the Helm chart means Kubernetes uses these local images.
minikube-build:
	eval $$(minikube docker-env) && \
	docker build -t wsc-producer -f producer/Dockerfile . && \
	docker build -t wsc-consumer -f consumer/Dockerfile .

# No sub-chart dependencies — infra runs via plain templates using Docker Hub images.
helm-deps:
	@echo "No sub-chart dependencies to resolve."

# Deploy (or upgrade) the full pipeline into the current kubectl context
k8s-up: helm-deps
	helm upgrade --install wsc-pipeline helm/wsc-pipeline/ \
		--wait --timeout=10m

# Tear down the release (keeps the Minikube cluster running)
k8s-down:
	helm uninstall wsc-pipeline

# Quick overview of all pipeline pods, jobs, and deployments
k8s-status:
	kubectl get pods,jobs,deployments -l app.kubernetes.io/instance=wsc-pipeline

# Re-run the producer by deleting the existing completed Job and recreating it.
# Kubernetes Jobs are immutable once created, so delete + recreate is the only way
# to re-run with the same job name.
k8s-run-producer:
	kubectl delete job wsc-pipeline-producer --ignore-not-found
	helm template wsc-pipeline helm/wsc-pipeline/ \
		--show-only templates/producer-job.yaml \
		| kubectl create -f -

# Tail logs from the producer Job (one-shot, reads all containers)
k8s-logs-producer:
	kubectl logs job/wsc-pipeline-producer --all-containers --tail=200

# Stream logs from the consumer Deployment
k8s-logs-consumer:
	kubectl logs deployment/wsc-pipeline-consumer -f
