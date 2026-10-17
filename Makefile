PTD_DATA_DIR ?= $(CURDIR)/data
export PTD_DATA_DIR

.PHONY: setup test c1 c2 pipeline

setup:
	uv sync --all-groups

test:
	uv run ruff check .
	uv run pytest -q

c1:
	uv run python -m pipeline c1

c2:
	uv run python -m pipeline c2

pipeline: c2
