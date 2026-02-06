"""
Token API routes.
Handles Deepgram short-lived token minting for client-side WebSocket connections.
"""
from fastapi import APIRouter, HTTPException, Depends
import httpx

from config import logger, DEEPGRAM_API_KEY, DEEPGRAM_PROJECT_ID
from services.rate_limit import RateLimiter

router = APIRouter(tags=["token"])


@router.get("/deepgram-token")
async def get_deepgram_token(
    _rate_limit=Depends(RateLimiter(requests=5, window=60, endpoint="deepgram-token")),
):
    """
    Mint a short-lived Deepgram API key for client-side WebSocket connections.
    
    Instead of exposing the real API key, this calls Deepgram's key creation API
    to generate a temporary key that auto-expires after 30 seconds — enough for
    the WebSocket handshake but useless if captured by an attacker.
    
    Rate limited to 5 requests/minute per IP.
    
    Returns:
        {"key": "temporary_api_key_string"}
    """
    if not DEEPGRAM_API_KEY:
        logger.error("DEEPGRAM_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Deepgram not configured")
    
    if not DEEPGRAM_PROJECT_ID:
        logger.error("DEEPGRAM_PROJECT_ID not configured")
        raise HTTPException(status_code=500, detail="Deepgram project not configured")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.deepgram.com/v1/projects/{DEEPGRAM_PROJECT_ID}/keys",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "comment": "short-lived-browser",
                    "scopes": ["usage:write"],
                    "time_to_live_in_seconds": 30,
                },
                timeout=10.0,
            )
        
        if response.status_code != 200:
            logger.error(
                f"Deepgram key creation failed: {response.status_code} - {response.text}"
            )
            raise HTTPException(
                status_code=502,
                detail="Failed to create temporary Deepgram key",
            )
        
        data = response.json()
        temp_key = data.get("key")
        
        if not temp_key:
            logger.error(f"Deepgram response missing 'key' field: {data}")
            raise HTTPException(
                status_code=502,
                detail="Invalid response from Deepgram",
            )
        
        logger.info("Minted short-lived Deepgram key (30s TTL)")
        return {"key": temp_key}
    
    except httpx.RequestError as e:
        logger.error(f"Network error minting Deepgram key: {e}")
        raise HTTPException(
            status_code=502,
            detail="Could not reach Deepgram API",
        )
