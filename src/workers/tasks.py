from celery import shared_task
from src.services.sync_service import AsyncService 
import asyncio
import logging


@shared_task
def main_periodic_tasks():
    """Runs every 15 min."""
    async_service = AsyncService()
    asyncio.run(holded_to_cegid(async_service))

async def holded_to_cegid(async_service: AsyncService) -> int:
    logging.getLogger(__name__).info("[Worker] Running holded_to_cegid service")
    
