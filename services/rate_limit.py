"""
Redis-backed rate limiter for FastAPI endpoints.
Uses Upstash Redis with fixed-window counting.
Works across Vercel serverless invocations (stateless).
"""
from fastapi import Request, HTTPException

from config import logger, redis_client


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP, accounting for Vercel's reverse proxy.
    
    Priority:
    1. x-real-ip (set by Vercel to the actual client IP)
    2. x-forwarded-for (first IP in the chain)
    3. request.client.host (direct connection, works for local dev)
    """
    # Vercel sets x-real-ip to the actual client IP
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    
    # Fallback: x-forwarded-for (first entry is the client)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    # Local dev fallback
    if request.client:
        return request.client.host
    
    return "unknown"


class RateLimiter:
    """
    FastAPI dependency that enforces per-IP rate limits using Redis.
    
    Usage:
        @router.get("/endpoint")
        async def my_endpoint(_rate_limit=Depends(RateLimiter(requests=5, window=60, endpoint="my-endpoint"))):
            ...
    
    Fail-open: If Redis is unavailable, requests are allowed through.
    """
    
    def __init__(self, requests: int, window: int, endpoint: str):
        """
        Args:
            requests: Maximum number of requests allowed in the window.
            window: Time window in seconds.
            endpoint: Identifier for the endpoint (used in Redis key).
        """
        self.requests = requests
        self.window = window
        self.endpoint = endpoint
    
    async def __call__(self, request: Request):
        if not redis_client:
            # Fail-open: no Redis means no rate limiting
            logger.warning("Rate limiter skipped: Redis not available")
            return
        
        ip = get_client_ip(request)
        key = f"rl:{self.endpoint}:{ip}"
        
        try:
            count = redis_client.incr(key)
            
            # Set expiry on first request in window
            if count == 1:
                redis_client.expire(key, self.window)
            
            if count > self.requests:
                # Get TTL so client knows when to retry
                ttl = redis_client.ttl(key)
                logger.warning(
                    f"Rate limit exceeded for {ip} on {self.endpoint}: "
                    f"{count}/{self.requests} (resets in {ttl}s)"
                )
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": ttl if ttl > 0 else self.window,
                    },
                    headers={"Retry-After": str(ttl if ttl > 0 else self.window)},
                )
        except HTTPException:
            # Re-raise rate limit errors
            raise
        except Exception as e:
            # Fail-open: if Redis errors out, allow the request
            logger.error(f"Rate limiter error for {self.endpoint}: {e}")
