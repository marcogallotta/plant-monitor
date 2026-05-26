.PHONY: test test-backend test-pi up down build

test: test-backend test-pi

test-backend:
	docker compose run --rm backend pytest tests/ -v

test-pi:
	docker compose run --rm pi pytest tests/ -v

up:
	docker compose up

down:
	docker compose down

build:
	docker compose build
