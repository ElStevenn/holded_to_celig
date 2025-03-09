from celery import shared_task
import asyncio
from src.services.sync_service import AsyncService

@shared_task
def main_periodic_tasks():
    """Runs every 15 min."""
    asyncio.run(holded_to_cegid())

async def holded_to_cegid():
    service = AsyncService()
    await service.fetch_holded_accounts(True)
