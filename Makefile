.PHONY: up down logs logs-worker logs-beat logs-redis restart-worker \
        restart-beat clean build celery-worker celery-beat shell test \
        down-app run-local

DOCKER_COMPOSE := docker compose
DOCKER          := docker
PROJECT_NAME    := holded_celig

up:
	$(DOCKER_COMPOSE) up --build -d

up-app:
	$(DOCKER_COMPOSE) up --build -d app

down:
	$(DOCKER_COMPOSE) down

down-app:
	$(DOCKER_COMPOSE) stop app
	$(DOCKER_COMPOSE) rm -f app

logs:
	$(DOCKER_COMPOSE) logs -f

logs-worker:
	$(DOCKER) logs -f celery_worker

logs-beat:
	$(DOCKER) logs -f celery_beat

logs-redis:
	$(DOCKER) logs -f redis_service

restart-worker:
	$(DOCKER_COMPOSE) restart celery_worker

restart-beat:
	$(DOCKER_COMPOSE) restart celery_beat

clean:
	$(DOCKER_COMPOSE) down -v --remove-orphans

build:
	$(DOCKER_COMPOSE) build

celery-worker:
	$(DOCKER_COMPOSE) run --rm celery_worker \
		celery -A src.workers.celery_config worker --loglevel=info

celery-beat:
	$(DOCKER_COMPOSE) run --rm celery_beat \
		celery -A src.workers.celery_config beat --loglevel=info

shell:
	$(DOCKER_COMPOSE) exec app /bin/sh

test:
	pytest tests/

run-local:
	@echo "Stopping Docker app container..."
	@$(DOCKER_COMPOSE) stop app 2>/dev/null || true
	@echo "Running app locally with venv..."
	@export PYTHONPATH=. && \
	 export REDIS_URL=redis://localhost:6379/0 && \
	 export BASIC_AUTH_USER=$${BASIC_AUTH_USER:-luis} && \
	 export BASIC_AUTH_PASS=$${BASIC_AUTH_PASS:-12345} && \
	 ./venv/bin/python src/quart_app/app.py
