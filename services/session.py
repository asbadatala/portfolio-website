"""
Session management using Upstash Redis.
Handles per-session chat history storage and retrieval.
"""
import json
from config import (
    logger,
    redis_client,
    SESSION_HISTORY_KEY_PREFIX,
    SESSION_TTL_SECONDS,
    MAX_HISTORY_MESSAGES,
)


async def get_session_history(session_id: str) -> list:
    """
    Retrieve chat history for a session from Redis.
    Returns list of {"role": "user"|"assistant", "content": "..."} dicts.
    """
    if not redis_client or not session_id:
        return []
    
    try:
        key = f"{SESSION_HISTORY_KEY_PREFIX}{session_id}"
        history_json = redis_client.get(key)
        if history_json:
            return json.loads(history_json)
        return []
    except Exception as e:
        logger.error(f"Error retrieving session history: {e}")
        return []


async def save_session_message(session_id: str, role: str, content: str):
    """
    Save a message to the session history in Redis.
    Maintains only the last MAX_HISTORY_MESSAGES messages.
    """
    if not redis_client or not session_id:
        return
    
    try:
        key = f"{SESSION_HISTORY_KEY_PREFIX}{session_id}"
        
        # Get existing history
        history = await get_session_history(session_id)
        
        # Add new message
        history.append({"role": role, "content": content})
        
        # Keep only last MAX_HISTORY_MESSAGES
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        
        # Save back to Redis with TTL
        redis_client.setex(key, SESSION_TTL_SECONDS, json.dumps(history))
        logger.info(f"Redis: Saved message to session {session_id}, total messages: {len(history)}")
    except Exception as e:
        logger.error(f"Error saving session message: {e}")


def format_chat_history(history: list, max_exchanges: int = 5) -> str:
    """
    Format chat history for inclusion in the prompt.
    Returns the last max_exchanges * 2 messages formatted as a string.
    """
    if not history:
        return ""
    
    # Get last N exchanges (N*2 messages)
    recent = history[-(max_exchanges * 2):]
    
    formatted_parts = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Assistant"
        # Truncate long messages for context
        content = msg["content"][:500] + "..." if len(msg["content"]) > 500 else msg["content"]
        formatted_parts.append(f"{role}: {content}")
    
    return "\n".join(formatted_parts)
