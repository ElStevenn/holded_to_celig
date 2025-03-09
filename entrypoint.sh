#!/bin/bash

set -e  # Exit on error

echo "Starting Celery Worker..."
celery -A src.workers.celery_config worker --loglevel=info &

echo "Starting Celery Beat..."
celery -A src.workers.celery_config beat --loglevel=info &

# Keep the container running
tail -f /dev/null
