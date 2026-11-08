# Cloud Computing Assignment Mini Project Makefile

PYTHON ?= python

.PHONY: help train clean-data test lint up down

help:
	@echo "Available targets:"
	@echo "  make train [SUBSET=50]   - Train student model (Sequence-Level Distillation)"
	@echo "  make clean-data          - Clean teacher shard outputs and compute SHA-256"
	@echo "  make test                - Run unit tests with pytest"
	@echo "  make lint                - Run ruff linter"
	@echo "  make up                  - Create k3d cluster and deploy all Kubernetes workloads"
	@echo "  make down                - Tear down cluster and all resources"

train:
	$(PYTHON) training/train.py --config training/config.yaml $(if $(SUBSET),--subset $(SUBSET),)

clean-data:
	$(PYTHON) worker/clean.py

test:
	pytest tests/

lint:
	ruff check service/ worker/ training/ tests/

up:
	k3d cluster create --config cluster/k3d.yaml || true
	kubectl apply -f k8s/namespaces.yaml
	kubectl apply -f k8s/secrets.yaml
	kubectl apply -f k8s/seaweedfs.yaml
	kubectl apply -f k8s/app.yaml
	kubectl apply -f k8s/hpa.yaml

down:
	k3d cluster delete cloud-cluster || true

