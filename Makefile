# Variables
DOCKER_COMPOSE = docker-compose
DOCKER = docker
PROJECT_NAME = holded_celig

# Start the application with Docker Compose
.PHONY: up
up:
	$(DOCKER_COMPOSE) up --build -d

# Stop the application
.PHONY: down
down:
	$(DOCKER_COMPOSE) down

# View application logs
.PHONY: logs
logs:
	$(DOCKER_COMPOSE) logs -f

# View specific logs for Celery Worker
.PHONY: logs-worker
logs-worker:
	$(DOCKER) logs -f celery_worker

# View specific logs for Celery Beat
.PHONY: logs-beat
logs-beat:
	$(DOCKER) logs -f celery_beat

# View specific logs for Redis
.PHONY: logs-redis
logs-redis:
	$(DOCKER) logs -f redis_service

# Restart only Celery Worker
.PHONY: restart-worker
restart-worker:
	$(DOCKER_COMPOSE) restart celery_worker

# Restart only Celery Beat
.PHONY: restart-beat
restart-beat:
	$(DOCKER_COMPOSE) restart celery_beat

# Clean volumes and containers (be careful with this command)
.PHONY: clean
clean:
	$(DOCKER_COMPOSE) down -v --remove-orphans

# Rebuild images
.PHONY: build
build:
	$(DOCKER_COMPOSE) build

# Manually run Celery Worker
.PHONY: celery-worker
celery-worker:
	$(DOCKER_COMPOSE) run --rm celery_worker celery -A config.celery_config worker --loglevel=info

# Manually run Celery Beat
.PHONY: celery-beat
celery-beat:
	$(DOCKER_COMPOSE) run --rm celery_beat celery -A config.celery_config beat --loglevel=info

# Run an interactive shell in the application
.PHONY: shell
shell:
	$(DOCKER_COMPOSE) exec app /bin/sh

# Run tests
.PHONY: test
test:
	pytest tests/
