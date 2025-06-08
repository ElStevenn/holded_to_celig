.PHONY: up down logs logs-worker logs-beat logs-redis restart-worker \
        restart-beat clean build celery-worker celery-beat shell test

DOCKER_COMPOSE := docker compose
DOCKER          := docker
PROJECT_NAME    := holded_celig

up:
	$(DOCKER_COMPOSE) up --build -d

down:
	$(DOCKER_COMPOSE) down

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
