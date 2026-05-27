.PHONY: test test-backend test-pi migrate seed up down build

TEST_COMPOSE := docker compose -p plant-monitoring-test -f docker-compose.test.yml

test: test-backend test-pi

test-backend:
	$(TEST_COMPOSE) run --rm backend pytest tests/ -v
	$(TEST_COMPOSE) down -v

test-pi:
	docker compose run --rm pi pytest tests/ -v

migrate:
	docker compose run --rm backend alembic upgrade head

seed:
	docker compose run --rm backend python scripts/seed.py --backend-url http://backend:8000

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build
