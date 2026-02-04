"""
Voice Chat API routes.
Handles voice-specific LLM chat with streaming for TTS consumption.
"""
import json
import asyncio
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx

from config import logger, jinja_env, OPENAI_API_KEY
from services.retrieval import retrieve_context
from services.session import get_session_history, save_session_message, format_chat_history

router = APIRouter(tags=["voice"])


class VoiceChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@router.post("/voice/chat")
async def voice_chat(request: VoiceChatRequest):
    """
    Process voice transcript and stream LLM response.
    
    This endpoint is designed for voice - it:
    - Uses the voice_prompt.j2 template (short, conversational responses)
    - Streams plain text (not SSE) for easy TTS consumption
    - Performs RAG retrieval for context
    - Saves to session history
    
    Request body:
        - message: str - The user's transcript
        - session_id: str (optional) - Session ID for history
        
    Returns:
        StreamingResponse with plain text chunks
    """
    message = request.message
    session_id = request.session_id
    
    if not message or not message.strip():
        return {"error": "Message is required"}
    
    logger.info(f"Voice chat processing (session: {session_id}): {message[:80]}...")
    
    # Start context retrieval in parallel
    context_task = asyncio.create_task(retrieve_context(message, k=6))
    
    # Get history and save user message
    chat_history = ""
    if session_id:
        # Get existing history first
        history = await get_session_history(session_id)
        chat_history = format_chat_history(history, max_exchanges=5)
        logger.info(f"Retrieved {len(history)} messages from session history")
        if chat_history:
            logger.info(f"Chat history preview: {chat_history[:200]}...")
        
        # Save current user message for next turn
        await save_session_message(session_id, "user", message)
        logger.info(f"Saved user message to session {session_id}")
    else:
        logger.warning("No session_id provided - history disabled")
    
    # Wait for context retrieval
    context, _ = await context_task
    
    # Render voice-optimized prompt
    template = jinja_env.get_template("voice_prompt.j2")
    system_content = template.render(context=context, chat_history=chat_history)
    
    async def generate():
        """Stream LLM response as plain text."""
        full_response = ""
        
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": message}
                        ],
                        "stream": True,
                        "max_completion_tokens": 150,  # Keep responses short for voice
                    },
                    timeout=30.0,
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_response += content
                                    yield content
                            except json.JSONDecodeError:
                                pass
        except Exception as e:
            logger.error(f"Error streaming LLM response: {e}")
            yield "[Error generating response]"
        
        # Save assistant response to history
        if session_id and full_response:
            await save_session_message(session_id, "assistant", full_response)
            logger.info(f"Saved assistant response to session {session_id}")
    
    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
        }
    )
