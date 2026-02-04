"""
Token API routes.
Handles Deepgram token minting for client-side WebSocket connections.
"""
from fastapi import APIRouter, HTTPException
import httpx

from config import logger, DEEPGRAM_API_KEY

router = APIRouter(tags=["token"])


@router.get("/deepgram-token")
async def get_deepgram_token():
    """
    Get Deepgram API key for client-side WebSocket connections.
    
    Note: Deepgram doesn't have a token minting API, so we return the API key directly.
    This endpoint should be rate-limited in production to prevent abuse.
    The API key is exposed to the client but only used for WebSocket connections.
    
    Returns:
        {"key": "api_key_string"}
    """
    if not DEEPGRAM_API_KEY:
        logger.error("DEEPGRAM_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Deepgram not configured")
    
    logger.info("Providing Deepgram API key for client WebSocket connection")
    return {"key": DEEPGRAM_API_KEY}
