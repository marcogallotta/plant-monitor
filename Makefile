.PHONY: test test-backend test-pi migrate up down build

test: test-backend test-pi

test-backend:
	docker compose run --rm backend pytest tests/ -v

test-pi:
	docker compose run --rm pi pytest tests/ -v

migrate:
	docker compose run --rm backend alembic upgrade head

seed:
	docker compose run --rm backend python scripts/seed.py --backend-url http://backend:8000

up:
	docker compose up

down:
	docker compose down

build:
	docker compose build
