# Any args passed to the make script, use with $(call args, default_value)
args = `arg="$(filter-out $@,$(MAKECMDGOALS))" && echo $${arg:-${1}}`
AUTO_DISCOVER_ARGS ?=
WORKER_ARGS ?=
PROD_DIST_DIR ?= .dist
PROD_PYTHON ?= .venv/bin/python
PROD_BINARY ?= .venv/bin/autochat
PROD_ARGS ?= serve
PROD_UV_CACHE_DIR ?= .uv-cache
TEST_AUTOCHAT_HOME ?= $(CURDIR)
TEST_LOCAL_DATA_DIR ?= $(TEST_AUTOCHAT_HOME)/local_data/tests
WIPE_AUTOCHAT_HOME := $(if $(AUTOCHAT_HOME),$(AUTOCHAT_HOME),$(HOME)/.local/share/autochat)
WIPE_LOCAL_DATA_DIR := $(WIPE_AUTOCHAT_HOME)/local_data

.PHONY: test test-changed test-coverage quality-dependencies format lint typecheck fix check auto-discover-models update-openapi-spec run dev-windows dev prod-run api-docs ingest wipe celery flower celery-worker arq-worker chat-worker tools-worker

########################################################################################################################
# Quality checks
########################################################################################################################

test:
	rm -rf "$(TEST_LOCAL_DATA_DIR)"/*
	AUTOCHAT_HOME=$(TEST_AUTOCHAT_HOME) PYTHONPATH=. uv run pytest tests $(PYTEST_ARGS) -v

test-changed:
	rm -rf "$(TEST_LOCAL_DATA_DIR)"/*
	AUTOCHAT_HOME=$(TEST_AUTOCHAT_HOME) PYTHONPATH=. uv run pytest tests --git-diff $(PYTEST_ARGS)

test-coverage:
	rm -rf "$(TEST_LOCAL_DATA_DIR)"/*
	AUTOCHAT_HOME=$(TEST_AUTOCHAT_HOME) PYTHONPATH=. uv run pytest tests --cov autochat --cov-report term --cov-report=html --cov-report xml --junit-xml=tests-results.xml

quality-dependencies:
	uv sync --inexact --extra dev

format: quality-dependencies
	uv run --no-sync ruff format . --check

lint: quality-dependencies
	uv run --no-sync ruff check autochat tests scripts

fix: quality-dependencies
	uv run --no-sync ruff check autochat tests scripts --fix
	uv run --no-sync ruff format .

typecheck: quality-dependencies
	uv run --no-sync ty check autochat scripts

check:
	$(MAKE) format
	$(MAKE) lint
	$(MAKE) typecheck

auto-discover-models:
	uv run python scripts/auto_discover_models.py $(AUTO_DISCOVER_ARGS)

update-openapi-spec:
	uv run python scripts/update_claude_specs.py


########################################################################################################################
# Run
########################################################################################################################

run:
	uv run autochat serve

dev-windows:
	uv run autochat serve --reload

dev:
	PYTHONUNBUFFERED=1 uv run autochat serve --reload --host 0.0.0.0 --port 8080

prod-run:
	rm -rf $(PROD_DIST_DIR)
	mkdir -p $(PROD_DIST_DIR)
	UV_CACHE_DIR=$(PROD_UV_CACHE_DIR) uv build --out-dir $(PROD_DIST_DIR)
	@if [ ! -x "$(PROD_PYTHON)" ]; then \
		echo "Python interpreter not found at $(PROD_PYTHON). Create the project venv first."; \
		exit 1; \
	fi
	@wheel="$$(ls -t $(PROD_DIST_DIR)/autochat-*.whl 2>/dev/null | head -n 1)"; \
	if [ -z "$$wheel" ]; then \
		echo "No built wheel found in $(PROD_DIST_DIR)."; \
		exit 1; \
	fi; \
	UV_CACHE_DIR=$(PROD_UV_CACHE_DIR) uv pip install --python $(PROD_PYTHON) --force-reinstall --no-deps "$$wheel"; \
	$(PROD_BINARY) $(PROD_ARGS)

########################################################################################################################
# Misc
########################################################################################################################

api-docs:
	AUTOCHAT_PROFILES=mock uv run python scripts/extract_openapi.py autochat.main:app --out docs/openapi.json

ingest:
	@uv run python scripts/ingest_folder.py $(call args)

wipe:
	@mkdir -p "$(WIPE_LOCAL_DATA_DIR)"
	@find "$(WIPE_LOCAL_DATA_DIR)" -mindepth 1 ! -name '.gitignore' -exec rm -rf {} +
########################################################################################################################
# Celery
########################################################################################################################

celery:
	AUTOCHAT_WORKER_MODE=celery ./scripts/worker_entrypoint $(WORKER_ARGS)

flower:
	AUTOCHAT_WORKER_MODE=flower ./scripts/worker_entrypoint $(WORKER_ARGS)

celery-worker:
	AUTOCHAT_WORKER_MODE=celery ./scripts/worker_entrypoint $(WORKER_ARGS)

arq-worker:
	AUTOCHAT_WORKER_MODE=arq ./scripts/worker_entrypoint $(WORKER_ARGS)

chat-worker:
	AUTOCHAT_WORKER_MODE=arq \
	AUTOCHAT_WORKER_APP_MODULE=autochat \
	AUTOCHAT_ARQ_QUEUE=chat \
	AUTOCHAT_ARQ_TASK_PACKAGES=autochat.arq.tasks.chat \
	AUTOCHAT_STATEFUL_WORKER_TYPE=chat \
	AUTOCHAT_WORKER_WARM_PROFILE=chat \
	./scripts/worker_entrypoint $(WORKER_ARGS)

tools-worker:
	AUTOCHAT_WORKER_MODE=celery \
	AUTOCHAT_WORKER_APP_MODULE=autochat \
	AUTOCHAT_CELERY_QUEUES=tools \
	AUTOCHAT_CELERY_TASK_PACKAGES=autochat.celery.tasks.tools \
	AUTOCHAT_STATEFUL_WORKER_TYPE=tools \
	AUTOCHAT_WORKER_WARM_PROFILE=tools \
	./scripts/worker_entrypoint $(WORKER_ARGS)
