PTD_DATA_DIR ?= $(CURDIR)/data
export PTD_DATA_DIR

PTD_C4_OUTPUT_DIR ?= $(PTD_DATA_DIR)/stage/c4
export PTD_C4_OUTPUT_DIR

C4_SELECTED = $(PTD_C4_OUTPUT_DIR)/selected_rates.csv
C5_RESULT = $(PTD_DATA_DIR)/stage/c5/c5result.csv

.PHONY: setup test c1 c2 c3 c4 c5 c6 pipeline

setup:
	uv sync --all-groups

test:
	uv run ruff check .
	uv run pytest -q

c1:
	uv run python -m pipeline c1

c2:
	uv run python -m pipeline c2

c3:
	uv run python -m pipeline c3

c4:
	uv run python -m pipeline c4 --output-dir "$(PTD_C4_OUTPUT_DIR)"

$(C4_SELECTED):
	$(MAKE) c4

c5: $(C4_SELECTED)
	uv run python -m pipeline c5

$(C5_RESULT):
	$(MAKE) c5

c6: $(C5_RESULT)
	uv run python -m pipeline c6

pipeline: c1 c2 c3 c4 c5 c6
