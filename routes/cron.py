"""
Cron job routes.
Handles scheduled tasks invoked by Vercel Cron.
"""
import os
import time
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from upstash_redis.asyncio import Redis as AsyncRedis
from upstash_vector import AsyncIndex

from config import logger, UPSTASH_NAMESPACE, UPSTASH_REDIS_URL, UPSTASH_REDIS_TOKEN

router = APIRouter(tags=["cron"])

CRON_SECRET = os.getenv("CRON_SECRET")
UPSTASH_VECTOR_URL = os.getenv("UPSTASH_VECTOR_REST_URL")
UPSTASH_VECTOR_TOKEN = os.getenv("UPSTASH_VECTOR_REST_TOKEN")

KEEP_ALIVE_KEY = "keep_alive:last_ping"
EMBEDDING_DIMENSIONS = 1536


async def _ping_redis() -> str:
    """Write a timestamp to Redis so the database registers real activity."""
    if not (UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN):
        raise RuntimeError("Redis credentials not configured")
    # Fresh client so a failed startup health check can't silently skip the ping
    redis = AsyncRedis(url=UPSTASH_REDIS_URL, token=UPSTASH_REDIS_TOKEN)
    await redis.set(KEEP_ALIVE_KEY, str(int(time.time())))
    return "ok"


async def _ping_vector() -> str:
    """Run a query against the RAG namespace so the index registers real activity."""
    if not (UPSTASH_VECTOR_URL and UPSTASH_VECTOR_TOKEN):
        raise RuntimeError("Vector credentials not configured")
    index = AsyncIndex(url=UPSTASH_VECTOR_URL, token=UPSTASH_VECTOR_TOKEN)
    # Dummy vector avoids an OpenAI embedding call
    results = await index.query(
        vector=[0.1] * EMBEDDING_DIMENSIONS,
        top_k=1,
        namespace=UPSTASH_NAMESPACE,
    )
    if not results:
        raise RuntimeError(f"Namespace '{UPSTASH_NAMESPACE}' returned no vectors")
    return "ok"


@router.get("/cron/keep-alive")
async def keep_alive(request: Request):
    """
    Ping Redis and the Vector index to prevent Upstash from hibernating or
    deleting them due to inactivity.
    Secured via CRON_SECRET so only Vercel Cron can invoke it.
    Returns 500 if any ping fails so failures surface in Vercel logs.
    """
    if CRON_SECRET:
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {CRON_SECRET}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    results = {}
    for name, ping in [("redis", _ping_redis), ("vector", _ping_vector)]:
        try:
            results[name] = await ping()
            logger.info(f"Keep-alive: {name} ping successful")
        except Exception as e:
            results[name] = f"error: {e}"
            logger.error(f"Keep-alive: {name} ping failed: {e}")

    failed = any(r != "ok" for r in results.values())
    return JSONResponse(
        status_code=500 if failed else 200,
        content={"status": "error" if failed else "ok", **results},
    )
