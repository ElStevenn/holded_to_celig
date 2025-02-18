# Variables
DOCKER_COMPOSE = docker-compose
DOCKER = docker
PROJECT_NAME = holded_celig

# Iniciar la aplicación con Docker Compose
.PHONY: up
up:
	$(DOCKER_COMPOSE) up --build -d

# Parar la aplicación
.PHONY: down
down:
	$(DOCKER_COMPOSE) down

# Ver logs de la aplicación
.PHONY: logs
logs:
	$(DOCKER_COMPOSE) logs -f

# Ver logs específicos de Celery Worker
.PHONY: logs-worker
logs-worker:
	$(DOCKER) logs -f celery_worker

# Ver logs específicos de Celery Beat
.PHONY: logs-beat
logs-beat:
	$(DOCKER) logs -f celery_beat

# Ver logs específicos de Redis
.PHONY: logs-redis
logs-redis:
	$(DOCKER) logs -f redis_service

# Reiniciar solo Celery Worker
.PHONY: restart-worker
restart-worker:
	$(DOCKER_COMPOSE) restart celery_worker

# Reiniciar solo Celery Beat
.PHONY: restart-beat
restart-beat:
	$(DOCKER_COMPOSE) restart celery_beat

# Limpiar volúmenes y contenedores (¡cuidado con este comando!)
.PHONY: clean
clean:
	$(DOCKER_COMPOSE) down -v --remove-orphans

# Construir las imágenes nuevamente
.PHONY: build
build:
	$(DOCKER_COMPOSE) build

# Ejecutar Celery Worker manualmente
.PHONY: celery-worker
celery-worker:
	$(DOCKER_COMPOSE) run --rm celery_worker celery -A config.celery_config worker --loglevel=info

# Ejecutar Celery Beat manualmente
.PHONY: celery-beat
celery-beat:
	$(DOCKER_COMPOSE) run --rm celery_beat celery -A config.celery_config beat --loglevel=info

# Ejecutar un shell interactivo en la aplicación
.PHONY: shell
shell:
	$(DOCKER_COMPOSE) exec app /bin/sh

# Ejecutar pruebas
.PHONY: test
test:
	pytest tests/
