# Reflex chatbot — common tasks. `make help` lists them.
SHELL := /bin/bash

DOCKERHUB_USER ?= ecrespo
IMAGE          ?= $(DOCKERHUB_USER)/reflex-chatbot
VERSION        := $(shell sed -nE 's/^version = "([^"]+)"/\1/p' pyproject.toml)
PLATFORMS      ?= linux/amd64,linux/arm64
PORT           ?= 3000
COMPOSE        ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help install dev prod lint format test check build \
        up up-ollama up-gpu down logs ps \
        docker-build docker-push docker-buildx \
        update bump release

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- local development ------------------------------------------------
install: ## Install dependencies (uv sync) and create .env if missing
	uv sync
	@test -f .env || { cp .env.example .env && echo "created .env"; }

dev: ## Run in development mode (hot reload) → http://localhost:3000
	uv run reflex run

prod: ## Run in production mode on a single port, like the Docker image
	uv run reflex run --env prod --single-port --backend-port $(PORT)

lint: ## ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-fix with ruff
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the test suite
	uv run pytest -q

check: lint test ## Lint + tests (what CI runs)

build: ## Build the PyPI distribution (dist/) and validate it
	rm -rf dist
	uv build
	uvx twine check --strict dist/*

# --- docker compose (profiles) ----------------------------------------
up: ## Chatbot only; LLM servers on the host or OpenRouter
	$(COMPOSE) up -d

up-ollama: ## Chatbot + Ollama (CPU) in compose  [profile: ollama]
	$(COMPOSE) --profile ollama up -d

up-gpu: ## Chatbot + Ollama on an NVIDIA GPU   [profile: ollama-gpu]
	$(COMPOSE) --profile ollama-gpu up -d

down: ## Stop every service of every profile (volumes are kept)
	$(COMPOSE) --profile '*' down

logs: ## Follow the chatbot logs
	$(COMPOSE) logs -f chatbot

ps: ## Status of the services
	$(COMPOSE) --profile '*' ps

# --- docker image -----------------------------------------------------
docker-build: ## Build the image for the local platform (:latest and :VERSION)
	docker build -t $(IMAGE):latest -t $(IMAGE):$(VERSION) .

docker-push: docker-build ## Build and push :latest and :VERSION to Docker Hub
	docker push $(IMAGE):$(VERSION)
	docker push $(IMAGE):latest

docker-buildx: ## Multi-arch build and push (amd64 + arm64)
	docker buildx build --platform $(PLATFORMS) \
		-t $(IMAGE):latest -t $(IMAGE):$(VERSION) --push .

# --- maintenance and release ------------------------------------------
update: ## Upgrade locked dependencies (uv.lock) and run the checks
	uv lock --upgrade
	uv sync
	$(MAKE) check

bump: ## Set a new version: make bump VERSION=0.2.0
	@[[ "$(VERSION)" =~ ^[0-9]+\.[0-9]+\.[0-9]+((a|b|rc)[0-9]+)?$$ ]] || \
		{ echo "usage: make bump VERSION=X.Y.Z"; exit 1; }
	uv version $(VERSION)
	sed -i -E 's/^__version__ = ".*"/__version__ = "$(VERSION)"/' reflex_chatbot/__init__.py
	@echo "version $(VERSION): review, commit and merge to main, then 'make release'"

release: ## Tag vVERSION on main and push it (triggers PyPI + Docker Hub)
	@[ "$$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "switch to main first"; exit 1; }
	@git diff --quiet && git diff --cached --quiet || { echo "working tree not clean"; exit 1; }
	git pull --ff-only
	git tag -a v$(VERSION) -m "v$(VERSION)"
	git push origin v$(VERSION)
