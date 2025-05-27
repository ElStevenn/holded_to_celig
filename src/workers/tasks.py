from celery import shared_task
from services.sync_service import AsyncService 
import asyncio


@shared_task
def main_periodic_tasks():
    """Runs every 15 min."""
    async_service = AsyncService()
    asyncio.run(holded_to_cegid(async_service))

async def holded_to_cegid(async_service: AsyncService) -> int:
    print("Runnign holded_to_cegid service")
    
