.PHONY: setup test c1 c2 pipeline api web up

setup:
	uv sync --all-groups

test:
	uv run ruff check .
	uv run pytest -q

c1:
	uv run python -m pipeline c1

c2:
	uv run python -m pipeline c2

pipeline:
	uv run python -m pipeline all

api:
	uvicorn app.main:app --app-dir api --reload

web:
	cd web && npm run dev

up:
	docker compose up --build
