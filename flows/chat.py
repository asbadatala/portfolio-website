"""
Chat flow - handles text-based conversation logic.
Orchestrates retrieval, LLM calls, and session management for chat.
"""
import json
import asyncio
from typing import Optional
from config import logger
from services.session import get_session_history, save_session_message, format_chat_history
from services.retrieval import retrieve_context
from services.llm import stream_unified_agent


class ChatFlow:
    """
    Chat flow with single unified agent.
    
    Flow:
    1. Get session history
    2. Retrieve context from vector store
    3. Unified agent handles routing + answering
    4. Save messages to session history
    
    The unified agent decides how to respond based on the message, context, and chat history.
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
    
    async def process_message(self, message: str):
        """
        Process a user message with a unified agent.
        
        Args:
            message: The user's message
            
        Yields:
            SSE-formatted data chunks
        """
        logger.info(f"ChatFlow processing (session: {self.session_id}): {message[:100]}...")
        
        # PARALLEL: Start both history retrieval and context retrieval simultaneously
        if self.session_id:
            history_task = asyncio.create_task(get_session_history(self.session_id))
        else:
            history_task = None
        
        context_task = asyncio.create_task(retrieve_context(message, k=6))
        
        # Background save user message (non-blocking)
        if self.session_id:
            asyncio.create_task(save_session_message(self.session_id, "user", message))
        
        # Wait for both parallel tasks
        if history_task:
            history = await history_task
        else:
            history = []
        chat_history = format_chat_history(history, max_exchanges=5)
        
        context, _ = await context_task
        
        # Step 3: Stream response from unified agent
        full_response = ""
        async for chunk in stream_unified_agent(message, context, chat_history):
            yield chunk
            
            # Extract content for saving to history
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    data = json.loads(chunk[6:])
                    if "content" in data:
                        full_response += data["content"]
                except Exception:
                    pass
        
        # Background save assistant response
        if self.session_id and full_response:
            asyncio.create_task(save_session_message(self.session_id, "assistant", full_response))
