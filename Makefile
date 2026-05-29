.PHONY: test test-backend test-pi test-js e2e-install test-e2e migrate seed up down build verify-up verify-down verify-reset tunnel

TEST_COMPOSE   := docker compose -p plant-monitoring-test   -f docker-compose.test.yml
VERIFY_COMPOSE := docker compose -p plant-monitoring-verify -f docker-compose.verify.yml
E2E_COMPOSE    := docker compose -p plant-monitoring-e2e    -f docker-compose.e2e.yml

test: test-backend test-pi test-js

test-backend:
	$(TEST_COMPOSE) run --rm backend pytest tests/ -v --cov=app --cov-report=term-missing
	$(TEST_COMPOSE) down -v

test-pi:
	docker compose run --rm pi pytest tests/ -v

test-js:
	cd backend && npm test

e2e-install:
	cd e2e && npm ci && npx playwright install --with-deps chromium

test-e2e:
	@bash -c 'set -e; \
	  ROOT=$$PWD; \
	  trap "docker compose -p plant-monitoring-e2e -f $$ROOT/docker-compose.e2e.yml down -v" EXIT; \
	  $(E2E_COMPOSE) up -d --build --wait; \
	  $(E2E_COMPOSE) run --rm backend alembic upgrade head; \
	  $(E2E_COMPOSE) run --rm backend python scripts/seed.py --backend-url http://backend:8000; \
	  cd e2e && npm test'

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

verify-up:
	$(VERIFY_COMPOSE) up -d --build

verify-down:
	$(VERIFY_COMPOSE) down -v

verify-reset:
	$(VERIFY_COMPOSE) down -v && $(VERIFY_COMPOSE) up -d --build

tunnel:
	@docker run --rm --network plant-monitoring_default cloudflare/cloudflared:latest \
	  tunnel --url http://backend:8000 2>&1 | \
	  while IFS= read -r line; do \
	    echo "$$line"; \
	    if echo "$$line" | grep -qo 'https://[a-z0-9-]*\.trycloudflare\.com'; then \
	      CF_URL=$$(echo "$$line" | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'); \
	      sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=$$CF_URL|" .env; \
	      docker compose up -d backend; \
	      echo "Tunnel live at $$CF_URL — backend restarted with PUBLIC_URL"; \
	    fi; \
	  done
