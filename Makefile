# =============================================================================
# Polymer Intelligence — repo-level make targets
#
# These are thin wrappers around scripts/compose; backend dev commands continue
# to run from backend/ (uv-managed). Targets here orchestrate the full stack.
# =============================================================================
.PHONY: help smoke

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

smoke: ## Run the full-stack production-compose smoke (D-02, synthetic data + placeholder env)
	bash tests/smoke/test_smoke_full_stack.sh
