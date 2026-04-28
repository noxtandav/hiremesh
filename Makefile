.PHONY: help up down logs ps build rebuild api-sh web-sh test backend-test backend-fmt backend-lint migrate makemigration venv

ENV_FILE := infra/.env
COMPOSE  := docker compose --env-file $(ENV_FILE) -f infra/docker-compose.yml

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

up: ## Boot the full stack
	$(COMPOSE) up -d --build

down: ## Stop & remove containers
	$(COMPOSE) down

logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=200

ps: ## Container status
	$(COMPOSE) ps

build: ## Build images
	$(COMPOSE) build

rebuild: ## Rebuild without cache
	$(COMPOSE) build --no-cache

api-sh: ## Open a shell in the api container
	$(COMPOSE) exec api bash

web-sh: ## Open a shell in the web container
	$(COMPOSE) exec web sh

migrate: ## Apply migrations inside the api container
	$(COMPOSE) exec api alembic upgrade head

makemigration: ## Autogenerate a migration. Usage: make makemigration m="message"
	$(COMPOSE) exec api alembic revision --autogenerate -m "$(m)"

backend-test: ## Run the backend test suite in the host venv
	cd backend && .venv/bin/pytest -q

backend-fmt: ## Format & lint-fix the backend
	cd backend && .venv/bin/ruff check --fix . && .venv/bin/ruff format .

backend-lint: ## Lint the backend
	cd backend && .venv/bin/ruff check .

venv: ## Create the host dev venv and install backend deps
	cd backend && uv venv .venv --python 3.13 && VIRTUAL_ENV=.venv uv pip install -e ".[dev]"

test: backend-test ## Alias for backend-test
