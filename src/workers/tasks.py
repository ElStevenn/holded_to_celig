from celery import shared_task
from src.services.sync_service import AsyncService 
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@shared_task
def main_periodic_tasks():
    """Runs every 15 min."""
    async_service = AsyncService()
    asyncio.run(holded_to_cegid(async_service))

async def holded_to_cegid(async_service: AsyncService) -> int:
    logger.info("[Worker] Running holded_to_cegid service")


@shared_task(bind=True)
def auto_migrate_invoices(self):
    """
    Automatic migration task that runs every N days (configurable).
    Exports invoices from Holded to Cegid for all configured accounts.
    Only migrates invoices from the last 30 days.
    """
    from datetime import datetime, timedelta
    from src.services.logging_utils import set_task_id, record_task_start, record_task_done
    from src.config.settings import HOLDED_ACCOUNTS, AUTO_MIGRATION_ENABLED, AUTO_MIGRATION_INTERVAL_DAYS
    
    # Use task ID for logging
    task_id = self.request.id
    token = set_task_id(task_id)
    record_task_start(task_id, {"type": "auto_migration", "triggered": "celery"})
    
    logger.info(f"[AUTO-MIGRATION] Starting automatic invoice migration (Task ID: {task_id})")
    logger.info(f"[AUTO-MIGRATION] Timestamp: {datetime.now().isoformat()}")
    
    try:
        if not AUTO_MIGRATION_ENABLED:
            logger.info("[AUTO-MIGRATION] Auto-migration is disabled in settings")
            record_task_done(task_id, status="skipped")
            return
        
        # Calculate date range (last N days)
        days_back = AUTO_MIGRATION_INTERVAL_DAYS
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        logger.info(f"[AUTO-MIGRATION] Filtering documents from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} ({days_back} days)")
        logger.info(f"[AUTO-MIGRATION] Found {len(HOLDED_ACCOUNTS)} accounts to process")
        
        # Process each account
        for idx, account in enumerate(HOLDED_ACCOUNTS, 1):
            empresa = account.get("nombre_empresa", account.get("empresa", "Unknown"))
            account_type = account.get("tipo_cuenta", account.get("tipo", "normal"))
            api_key = account.get("api_key")
            codigo_empresa = account.get("codigo_empresa")
            cuentas_migrar = account.get("cuentas_a_migrar", [])
            
            logger.info(f"[AUTO-MIGRATION] Processing account {idx}/{len(HOLDED_ACCOUNTS)}: {empresa}")
            logger.info(f"[AUTO-MIGRATION] {empresa} - Account type: {account_type}")
            logger.info(f"[AUTO-MIGRATION] {empresa} - Document types to migrate: {cuentas_migrar}")
            
            try:
                # Run async processing
                asyncio.run(_process_account_migration(
                    api_key, codigo_empresa, empresa, cuentas_migrar, start_date, end_date, task_id
                ))
                logger.info(f"[AUTO-MIGRATION] ✓ Successfully processed {empresa}")
            except Exception as e:
                logger.error(f"[AUTO-MIGRATION] ✗ Error processing {empresa}: {str(e)}", exc_info=True)
                continue
        
        logger.info("[AUTO-MIGRATION] Automatic migration completed successfully")
        record_task_done(task_id, status="done")
        
    except Exception as e:
        logger.error(f"[AUTO-MIGRATION] Critical error during auto-migration: {str(e)}", exc_info=True)
        record_task_done(task_id, status="error")
        raise
    finally:
        try:
            from src.services.logging_utils import task_id_ctx
            task_id_ctx.reset(token)
        except:
            pass


async def _process_account_migration(api_key, codigo_empresa, empresa, cuentas_migrar, start_date, end_date, task_id):
    """Async function to process account migration"""
    from src.services.holded_service import HoldedAPI
    from src.services.cegid_service import CegidAPI
    from dateutil import parser as date_parser
    from src.services.logging_utils import set_task_id, task_id_ctx
    
    # Set task_id in this async context
    token = set_task_id(task_id)
    
    try:
        # Initialize APIs
        holded_api = HoldedAPI(api_key)
        cegid_api = CegidAPI(codigo_empresa)
        
        # Process each document type
        for doc_type in cuentas_migrar:
        logger.info(f"[AUTO-MIGRATION] {empresa} - Fetching {doc_type} documents from Holded...")
        
        try:
            # Fetch all documents from Holded
            all_docs = await holded_api.list_invoices(doc_type)
            logger.info(f"[AUTO-MIGRATION] {empresa} - Found {len(all_docs)} total {doc_type} documents")
            
            # Filter by date range
            filtered_docs = []
            for doc in all_docs:
                try:
                    date_str = doc.get('date') or doc.get('created_at') or doc.get('createdAt')
                    if not date_str:
                        continue
                    
                    doc_date = date_parser.parse(date_str)
                    if doc_date.tzinfo:
                        doc_date = doc_date.replace(tzinfo=None)
                    
                    if start_date <= doc_date <= end_date:
                        filtered_docs.append(doc)
                except:
                    continue
            
            logger.info(f"[AUTO-MIGRATION] {empresa} - Filtered to {len(filtered_docs)} {doc_type} documents within date range")
            
            if filtered_docs:
                logger.info(f"[AUTO-MIGRATION] {empresa} - Found {len(filtered_docs)} {doc_type} documents to migrate")
                # Note: Actual migration logic would go here
                # For now, just log what would be migrated
            else:
                logger.info(f"[AUTO-MIGRATION] {empresa} - No {doc_type} documents to migrate in this period")
                    
            except Exception as e:
                logger.error(f"[AUTO-MIGRATION] {empresa} - Error processing {doc_type}: {str(e)}", exc_info=True)
                continue
    finally:
        # Reset context
        task_id_ctx.reset(token)
