VENV := .venv
ifeq ($(OS),Windows_NT)
PY ?= py -3.12
BIN := $(VENV)/Scripts
else
PY ?= python3.12
BIN := $(VENV)/bin
endif

.PHONY: infra infra-down install model seed ingest ask test lint

infra:            ## start MinIO (+ bucket) and Qdrant
	docker compose up -d

infra-down:
	docker compose down

install:
	@if command -v uv >/dev/null; then \
		uv venv --python 3.12 $(VENV) && uv pip install --python $(BIN)/python -e ".[dev]"; \
	else \
		$(PY) -m venv $(VENV) && $(BIN)/pip install -U pip && $(BIN)/pip install -e ".[dev]"; \
	fi
	$(BIN)/zenml init

model:            ## one-time online download of the embedding model
	$(BIN)/python scripts/download_model.py

seed:
	$(BIN)/python scripts/seed_minio.py

ingest:
	$(BIN)/klausel-ingest

ask:
	$(BIN)/klausel-query --show-context "$(Q)"

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check src scripts tests && $(BIN)/ruff format --check src scripts tests
