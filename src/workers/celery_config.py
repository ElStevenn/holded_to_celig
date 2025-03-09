import celery as celery_lib
from celery.schedules import crontab
from src.config.settings import REDIS_URL

celery_app = celery_lib.Celery(
    'tasks',
    broker=REDIS_URL
)
celery_app.conf.timezone = 'UTC'

# Autodiscover tasks from `src.workers` package
celery_app.autodiscover_tasks(['src.workers'])

celery_app.conf.beat_schedule = {
    "run-every-15-minutes": {
        "task": "src.workers.tasks.main_periodic_tasks",
        "schedule": crontab(minute='*/15'),
    },
}
