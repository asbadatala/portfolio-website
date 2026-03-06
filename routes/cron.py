"""
Cron job routes.
Handles scheduled tasks invoked by Vercel Cron.
"""
import os
from fastapi import APIRouter, Request, HTTPException

from config import logger, redis_client

router = APIRouter(tags=["cron"])

CRON_SECRET = os.getenv("CRON_SECRET")


@router.get("/cron/keep-alive")
async def keep_alive(request: Request):
    """
    Ping Redis to prevent Upstash from deleting the instance due to inactivity.
    Secured via CRON_SECRET so only Vercel Cron can invoke it.
    """
    if CRON_SECRET:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {CRON_SECRET}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    if not redis_client:
        logger.warning("Keep-alive: Redis client not available")
        return {"status": "skipped", "reason": "redis_client is None"}

    try:
        redis_client.ping()
        logger.info("Keep-alive: Redis ping successful")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Keep-alive: Redis ping failed: {e}")
        return {"status": "error", "reason": str(e)}
