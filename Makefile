.PHONY: test api web up

test:
	python3 -m unittest discover -s api/tests -v

api:
	uvicorn app.main:app --app-dir api --reload

web:
	cd web && npm run dev

up:
	docker compose up --build
