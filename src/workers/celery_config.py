import celery
from celery.schedules import crontab
from src.config.settings import REDIS_URL, AUTO_MIGRATION_INTERVAL_DAYS, AUTO_MIGRATION_ENABLED

celery_app = celery.Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.timezone = "UTC"
celery_app.autodiscover_tasks(["src.workers"])

# Build beat schedule dynamically
beat_schedule = {
    "run-every-15-minutes": {
        "task": "src.workers.tasks.main_periodic_tasks",
        "schedule": crontab(minute="*/15"),   # execute every 15 min
    },
}

# Add auto-migration task if enabled
if AUTO_MIGRATION_ENABLED:
    # Schedule to run every N days at midnight (configurable via AUTO_MIGRATION_INTERVAL_DAYS)
    # For monthly execution on last day, use: crontab(0, 0, day_of_month='28-31')
    # For now, we'll use a simple interval: every N days at 00:00
    beat_schedule["auto-migrate-invoices"] = {
        "task": "src.workers.tasks.auto_migrate_invoices",
        "schedule": crontab(hour=0, minute=0, day_of_month=f"*/{AUTO_MIGRATION_INTERVAL_DAYS}"),
        "options": {
            "expires": 3600 * 24,  # Task expires after 24 hours if not executed
        }
    }

celery_app.conf.beat_schedule = beat_schedule
