"""
Chat API routes.
Handles text-based chat endpoints.
"""
import uuid
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from config import logger
from flows.chat import ChatFlow

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/session")
async def create_session():
    """Create a new chat session and return session ID."""
    session_id = str(uuid.uuid4())
    logger.info(f"Created new session: {session_id}")
    return {"session_id": session_id}


@router.post("/chat")
async def chat(request: Request):
    """
    Process a chat message and stream the response.
    
    Request body:
        - message: str - The user's message
        - session_id: str (optional) - Session ID for history
        
    Returns:
        StreamingResponse with SSE-formatted data
    """
    body = await request.json()
    message = body.get("message")
    session_id = body.get("session_id")
    
    if not message:
        return {"error": "Message is required"}
    
    # Use single-agent flow
    flow = ChatFlow(session_id=session_id)
    
    return StreamingResponse(
        flow.process_message(message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
