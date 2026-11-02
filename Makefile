# Field Return Triage - one command per job.
#
# `make all` rebuilds data checks, the index, trend, results and the page in replay mode
# (no key, no network). `make release-check` is what CI runs.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON := uv run python
PYTEST := uv run pytest

.PHONY: help setup fetch-data data data-check index index-cached test lint format typecheck scan-forbidden \
        scan-secrets facts eval-replay probe live trend results page-data page all \
        release-check clean

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Create the venv and install exact locked versions
	uv sync

fetch-data: ## Download the NHTSA snapshot into data/raw/
	uv run python scripts/fetch_nhtsa.py

data: ## Derive the library, eval set and trend tables
	uv run python -m field_return_triage.data.cli

data-check: ## Verify the committed data against data/CHECKSUMS.txt
	uv run python -m field_return_triage.pipeline.cli data-check

index: ## Embed the library into the local vector cache
	uv run --extra index python -m field_return_triage.similar.cli

index-cached: ## Reuse the embedding index, build it only when missing
	uv run --extra index python -m field_return_triage.pipeline.cli index-cached

test: ## Run the test suite with the network blocked
	$(PYTEST) -q

lint: ## Ruff lint and format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Apply Ruff formatting
	uv run ruff check --fix .
	uv run ruff format .

typecheck: ## Strict mypy on src/
	uv run mypy

scan-forbidden: ## Fail on a forbidden name in tracked files or recent commits
	$(PYTHON) scripts/scan_forbidden.py

scan-secrets: ## Fail on credential-looking strings
	$(PYTHON) scripts/scan_secrets.py

facts: ## Check every published number against the results file that proves it
	$(PYTHON) scripts/check_facts.py

eval-replay: ## Score the eval set from committed recordings
	uv run --extra index python -m field_return_triage.pipeline.cli eval-replay

probe: ## One paid call per locked model; records recordings/probes.json
	uv run python -m field_return_triage.pipeline.cli probe

live: ## The one paid run; needs a key and the budget
	uv run python -m field_return_triage.pipeline.cli live

trend: ## Detect weekly spikes and backtest them against recalls
	uv run python -m field_return_triage.trend.cli

results: ## Export results and the summary from replay
	uv run --extra index python -m field_return_triage.pipeline.cli results

page-data: ## Build results/page/page-data.json
	uv run python -m field_return_triage.report.cli page-data

page: ## Build dist/field-return-triage/index.html
	uv run python -m field_return_triage.report.cli page

all: data-check index-cached trend results ## Rebuild everything in replay mode
	@if [ -d src/field_return_triage/report ]; then \
		$(MAKE) page-data page; \
	else \
		echo "all: results are ready; the report package is missing, so the page is not built"; \
	fi

release-check: lint typecheck test scan-forbidden scan-secrets facts ## CI gate
	@test -f LICENSE && grep -q "MIT License" LICENSE || { echo "LICENSE (MIT) missing"; exit 1; }
	@echo "release-check: green"

clean: ## Remove caches (never touches results/, recordings/ or data/)
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -not -path "./.venv/*" -prune -exec rm -rf {} +
