# AEGIS — developer convenience targets.
# Cross-platform (Make + bash). On Windows use Git Bash, WSL, or Cygwin.

.PHONY: help up down logs api-shell migrate makemigration test lint fmt typecheck catalogue-validate catalogue-import dev-login seed-dev-tenant clean

help:        ## Show this help
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up:          ## Start the full local stack
	docker compose up -d

down:        ## Stop the stack (preserves volumes)
	docker compose down

destroy:     ## Stop the stack and destroy volumes
	docker compose down -v

logs:        ## Tail logs for all services
	docker compose logs -f

api-shell:   ## Open a shell inside the API container
	docker compose exec api bash

migrate:     ## Apply Alembic migrations
	docker compose exec api alembic upgrade head

makemigration: ## Create a new (empty) Alembic migration; usage: make makemigration MSG="add table x"
	docker compose exec api alembic revision -m "$(MSG)"

test:        ## Run all API tests
	docker compose exec api pytest -q

lint:        ## Lint API and Web
	docker compose exec api ruff check .
	cd web && npm run lint --if-present

fmt:         ## Auto-format API
	docker compose exec api ruff format .
	docker compose exec api ruff check --fix .

typecheck:   ## Type-check API and Web
	docker compose exec api mypy app
	cd web && npm run typecheck

catalogue-validate: ## Validate every catalogue YAML against schema
	cd catalogue && python -m scripts.validate

catalogue-import: ## Validate + upsert every catalogue YAML into ai_services / ai_providers
	docker compose exec api python /workspace/catalogue/scripts/importer.py -v

framework-import: ## Validate + upsert every compliance framework YAML into compliance_frameworks / compliance_controls
	docker compose exec api python /workspace/catalogue/scripts/import_frameworks.py -v

threats-validate: ## Validate every catalogue/threats/**/*.yaml against schema.yaml
	python catalogue/scripts/threats_validate.py

threats-digest: ## Compute the deterministic SHA-256 digest of the threat inventory
	python catalogue/scripts/threats_digest.py

threats-digest-check: ## CI gate — fail if the inventory drifts from the pinned digest
	python catalogue/scripts/threats_digest.py --check

threats-digest-update: ## Re-pin the digest after an intentional catalogue edit
	python catalogue/scripts/threats_digest.py --update

threats-import: ## Validate + upsert every threat YAML into the threats table (drift-checked)
	docker compose exec api python /workspace/catalogue/scripts/threats_importer.py -v

dev-login: ## Fetch a JWT from the dev Keycloak realm and print the browser snippet
	@bash infra/scripts/dev-login.sh

seed-dev-tenant: ## Insert the default dev tenant (matches the JWT tenant_id claim)
	@bash infra/scripts/seed-dev-tenant.sh

clean:       ## Remove caches and build artefacts
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf api/.mypy_cache web/dist web/node_modules/.vite
