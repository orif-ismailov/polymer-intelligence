# =============================================================================
# Polymer Intelligence — repo-level make targets
#
# These are thin wrappers around scripts/compose; backend dev commands continue
# to run from backend/ (uv-managed). Targets here orchestrate the full stack.
# =============================================================================
.PHONY: help dev dev-stop smoke webapp-bundle portal-bundle env-sync

# --env-file .env: Compose otherwise looks for the interpolation .env next to the
# compose file (deploy/), not the repo root — leaving ${POSTGRES_PASSWORD} etc.
# empty. This also activates COMPOSE_PROJECT_NAME from .env so volume names match.
COMPOSE ?= docker compose --env-file .env -f deploy/docker-compose.yml

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev: ## Run the WHOLE local stack (infra + api + worker + beat + portal + dashboard)
	@bash scripts/dev.sh

dev-stop: ## Stop the infra containers `make dev` leaves running
	@docker stop pi-pg pi-redis pi-minio

smoke: ## Run the full-stack production-compose smoke (D-02, synthetic data + placeholder env)
	bash tests/smoke/test_smoke_full_stack.sh

webapp-bundle: ## Build the Telegram Web App and load it into the webapp_static volume (nginx serves /webapp/)
	$(COMPOSE) --profile build run --rm --build webapp-build

env-sync: ## Refresh the [panel: X] markers in deploy/.env.example from the settings specs
# Runs in the backend venv because it reads `Settings` and the SettingSpec list.
# `test_env_contract_sync` fails when this is out of date, so CI says to run it.
	uv run --project backend python scripts/sync_env_example.py

portal-bundle: ## Rebuild + restart the SSR portal service (nginx proxies cabinet.*)
	# The portal is no longer a bundle copied into a volume: it is a long-running
	# Node process that server-renders the public marketplace routes. The target
	# keeps its name so existing runbooks and muscle memory still work.
	$(COMPOSE) build portal
	$(COMPOSE) up -d portal
