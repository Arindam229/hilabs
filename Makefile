PTD_DATA_DIR ?= $(CURDIR)/data
export PTD_DATA_DIR

PTD_RATE_FILE ?= $(PTD_DATA_DIR)/hilabs_dataset_2026-10-17.zip
export PTD_RATE_FILE

PTD_RATE_MEMBER ?= hilabs_dataset_2026-10-17/centene/in_network/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json
export PTD_RATE_MEMBER

PTD_C4_OUTPUT_DIR ?= $(PTD_DATA_DIR)/stage/c4
export PTD_C4_OUTPUT_DIR

.PHONY: setup test c1 c2 c4 pipeline

setup:
	uv sync --all-groups

test:
	uv run ruff check .
	uv run pytest -q

c1:
	uv run python -m pipeline c1

c2:
	uv run python -m pipeline c2

c4: c2
	uv run python -m pipeline c4 --rate-file "$(PTD_RATE_FILE)" --rate-member "$(PTD_RATE_MEMBER)" --output-dir "$(PTD_C4_OUTPUT_DIR)"

pipeline: c1 c2 c4