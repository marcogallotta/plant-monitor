.PHONY: test test-backend test-pi test-js e2e-install test-e2e migrate seed ingest-suggestions submit-tagging-batch ingest-tagging-batch agreement-gate compare-ab-runs up down build verify-up verify-down verify-reset tunnel

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

submit-tagging-batch:
	@set -a && . ./.env && set +a && docker compose run --rm \
	  -e ANTHROPIC_API_KEY -e ASSISTANT_API_TOKEN \
	  backend python scripts/submit_tagging_batch.py $(ARGS)

ingest-tagging-batch:
	@test -n "$(RUN_ID)" || (echo "Usage: make ingest-tagging-batch RUN_ID=<run_id> [ARGS='--poll']" && exit 1)
	@set -a && . ./.env && set +a && docker compose run --rm \
	  -e ANTHROPIC_API_KEY -e ASSISTANT_API_TOKEN \
	  backend python scripts/ingest_tagging_batch.py --run-id $(RUN_ID) $(ARGS)

agreement-gate:
	@test -n "$(RUN_ID)" || (echo "Usage: make agreement-gate RUN_ID=<run_id> [ARGS='']" && exit 1)
	@set -a && . ./.env && set +a && docker compose run --rm \
	  -e ANTHROPIC_API_KEY -e ASSISTANT_API_TOKEN \
	  backend python scripts/agreement_gate.py --run-id $(RUN_ID) $(ARGS)

compare-ab-runs:
	@test -n "$(RICH)" || (echo "Usage: make compare-ab-runs RICH=ab_rich THIN=ab_thin" && exit 1)
	@test -n "$(THIN)" || (echo "Usage: make compare-ab-runs RICH=ab_rich THIN=ab_thin" && exit 1)
	@set -a && . ./.env && set +a && docker compose run --rm \
	  -e ASSISTANT_API_TOKEN \
	  -e BACKEND_URL=http://backend:8000 \
	  backend python scripts/compare_ab_runs.py --rich $(RICH) --thin $(THIN) $(ARGS)

ingest-suggestions:
	@test -n "$(FILE)" || (echo "Usage: make ingest-suggestions FILE=path/to/suggestions.json" && exit 1)
	docker compose run --rm -v $(CURDIR)/$(FILE):/tmp/suggestions.json backend python scripts/ingest_suggestions.py /tmp/suggestions.json

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
	@docker rm -f plant-monitoring-quicktunnel 2>/dev/null || true
	@docker run -d --name plant-monitoring-quicktunnel --network plant-monitoring_default \
	  cloudflare/cloudflared:latest tunnel --url http://backend:8000 > /dev/null
	@echo "Waiting for tunnel URL..."
	@for i in $$(seq 1 30); do \
	  CF_URL=$$(docker logs plant-monitoring-quicktunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | head -1); \
	  if [ -n "$$CF_URL" ]; then \
	    sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=$$CF_URL|" .env; \
	    docker compose up -d backend; \
	    echo "Tunnel live at $$CF_URL"; \
	    break; \
	  fi; \
	  sleep 1; \
	done
