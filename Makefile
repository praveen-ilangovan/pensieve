##################
###   INSTALL  ###
.PHONY: install
install: ## Install the poetry environment + pre-commit hooks
	@echo "🚀 Creating virtual environment using poetry"
	@poetry install
	@poetry run pre-commit install

##################
##  PRECOMMIT  ###
.PHONY: check
check: ## Run code quality tools (ruff lint+fmt, mypy)
	@echo "🚀 Checking poetry lock consistency"
	@poetry check --lock
	@echo "🚀 Running pre-commit on all files"
	@poetry run pre-commit run --all-files

##################
###### TEST ######
.PHONY: unittest
unittest: ## Run unit tests
	@echo "🚀 Running unit tests"
	@poetry run pytest tests/unittests

.PHONY: test-integration
test-integration: ## Run integration tests
	@echo "🚀 Running integration tests"
	@poetry run pytest tests/integrations

.PHONY: test
test: ## Run all tests
	@poetry run pytest

##################
######  CLI  #####
# Store location comes from .env (PENSIEVE_HOME=.local/manual), so these are just
# thin wrappers — `poetry run pensieve ...` works directly in the repo too.
.PHONY: manual
manual: ## Run the CLI against the local store (make manual ARGS="create --stream recs")
	@poetry run pensieve $(ARGS)

.PHONY: quick-run
quick-run: ## Seed the local store with sample streams
	@poetry run python manual_runners/quick_run.py

.PHONY: mcp
mcp: ## Run the MCP server (stdio) — for wiring into an agent
	@poetry run pensieve-mcp

##################
#####  HELP  #####
.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
