import asyncio
import logging
from datetime import datetime
from sqlalchemy import select
from arq import create_pool
from arq.connections import RedisSettings
from config import settings

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("outbox_poller")

# Import Database Session and Models
from models import AsyncSessionLocal, Document

async def poll_and_reconcile_outbox():
    """Polls PostgreSQL for failed queues and attempts to re-enqueue them into arq."""
    logger.info("Initializing Outbox Reconciliation Poller...")
    
    redis_pool = None
    
    while True:
        try:
            # 1. Try to connect to Redis/arq if not connected
            if redis_pool is None:
                redis_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
                logger.info("✓ Connected to Redis broker.")

            # 2. Open Async Postgres Session
            async with AsyncSessionLocal() as db:
                # Query for any documents stuck in QUEUING_FAILED state
                result = await db.execute(
                    select(Document).where(Document.status == "QUEUING_FAILED").order_by(Document.created_at.asc())
                )
                failed_docs = result.scalars().all()

                if failed_docs:
                    logger.info(f"Found {len(failed_docs)} documents pending outbox recovery.")

                for doc in failed_docs:
                    logger.info(f"Attempting to re-enqueue document: {doc.filename} (ID: {doc.id})")
                    try:
                        # Attempt to push to arq
                        await redis_pool.enqueue_job("process_document", str(doc.id))
                        
                        # Enqueued successfully! Mark as QUEUED in database
                        doc.status = "QUEUED"
                        doc.updated_at = datetime.utcnow()
                        await db.commit()
                        logger.info(f"✓ Document {doc.filename} successfully recovered and queued!")
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to connect to Redis during recovery of doc {doc.id}: {e}")
                        # Redis is still down, abort this round and wait
                        break

        except Exception as e:
            logger.error(f"Error in outbox polling loop: {e}")
            redis_pool = None  # Reset Redis pool connection

        # Sleep for 10 seconds before the next polling cycle
        await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(poll_and_reconcile_outbox())
    except KeyboardInterrupt:
        logger.info("Outbox poller stopped by user.")
