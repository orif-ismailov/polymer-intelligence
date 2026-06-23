# =============================================================================
# Polymer Intelligence — repo-level make targets
#
# These are thin wrappers around scripts/compose; backend dev commands continue
# to run from backend/ (uv-managed). Targets here orchestrate the full stack.
# =============================================================================
.PHONY: help smoke webapp-bundle

# --env-file .env: Compose otherwise looks for the interpolation .env next to the
# compose file (deploy/), not the repo root — leaving ${POSTGRES_PASSWORD} etc.
# empty. This also activates COMPOSE_PROJECT_NAME from .env so volume names match.
COMPOSE ?= docker compose --env-file .env -f deploy/docker-compose.yml

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

smoke: ## Run the full-stack production-compose smoke (D-02, synthetic data + placeholder env)
	bash tests/smoke/test_smoke_full_stack.sh

webapp-bundle: ## Build the Telegram Web App and load it into the webapp_static volume (nginx serves /webapp/)
	$(COMPOSE) --profile build run --rm --build webapp-build
