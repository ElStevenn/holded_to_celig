#!/bin/bash

# Inicia Celery Worker en segundo plano
celery -A config.celery_config worker --loglevel=info &

# Inicia Celery Beat para ejecutar tareas periódicas en segundo plano
celery -A config.celery_config beat --loglevel=info &

# Ejecuta la API o el servicio principal (ajusta esto si usas FastAPI o Flask)
uvicorn main:app --host 0.0.0.0 --port 8000
