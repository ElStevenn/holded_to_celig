import celery
from celery.schedules import crontab
from src.config.settings import REDIS_URL

celery_app = celery.Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.timezone = "UTC"
celery_app.autodiscover_tasks(["src.workers"])

celery_app.conf.beat_schedule = {
    "run-every-15-minutes": {
        "task": "src.workers.tasks.main_periodic_tasks",
        "schedule": crontab(minute="*/1"),   # execute every 15 min
    },
}
