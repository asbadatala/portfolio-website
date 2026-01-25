"""
Chat flow - handles text-based conversation logic.
Orchestrates routing, retrieval, LLM calls, and session management for chat.
"""
import json
import asyncio
from typing import Optional
from config import logger
from services.session import get_session_history, save_session_message, format_chat_history
from services.retrieval import retrieve_context, interpret_user_query
from services.llm import stream_speaker_response, stream_unified_agent


class ChatFlow:
    """
    Orchestrates the chat conversation flow with early exit capability.
    
    Flow:
    1. Get session history
    2. Interpreter Agent decides: direct response OR needs context
    3a. If direct_response: Return immediately (early exit)
    3b. If needs_context: Retrieve context from vector store
    4. Stream response from Speaker Agent
    5. Save messages to session history
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
    
    async def process_message(self, message: str):
        """
        Process a user message and return a streaming response generator.
        Optimized with parallelization for reduced latency.
        
        Args:
            message: The user's message
            
        Yields:
            SSE-formatted data chunks
        """
        logger.info(f"Chat flow processing (session: {self.session_id}): {message[:100]}...")
        
        # OPTIMIZATION: Get session history first (needed for interpreter to understand follow-ups)
        if self.session_id:
            history = await get_session_history(self.session_id)
        else:
            history = []
        chat_history = format_chat_history(history, max_exchanges=5)
        
        if chat_history:
            logger.info(f"Including {len(history)} messages from session history")
        
        # OPTIMIZATION: Background save user message (non-blocking)
        if self.session_id:
            asyncio.create_task(save_session_message(self.session_id, "user", message))
        
        # Interpreter Agent decides routing (now with chat history for follow-up understanding)
        interpreter_result = await interpret_user_query(message, chat_history)
        action = interpreter_result.get("action", "needs_context")
        
        # Step 3a: Early exit for direct responses (greetings, simple queries)
        if action == "direct_response":
            direct_response = interpreter_result.get("response", "")
            logger.info(f"Early exit: Direct response for '{message[:50]}...'")
            
            # Stream the direct response word by word to match Speaker Agent behavior
            words = direct_response.split()
            for i, word in enumerate(words):
                # Add space before word (except first word)
                chunk = f" {word}" if i > 0 else word
                yield f"data: {json.dumps({'content': chunk})}\n\n"
                # Small delay to simulate streaming (optional, can be removed for faster response)
                await asyncio.sleep(0.02)  # 20ms delay between words
            
            yield "data: [DONE]\n\n"
            
            # OPTIMIZATION: Background save assistant response (non-blocking)
            if self.session_id and direct_response:
                asyncio.create_task(save_session_message(self.session_id, "assistant", direct_response))
            return
        
        # Step 3b: Needs context - go through RAG
        refined_query = interpreter_result.get("query", message)
        # Use normalized question if available, otherwise fall back to original message
        normalized_question = interpreter_result.get("question", message)
        
        # Step 4: Retrieve relevant context from vector store
        context, retrieved_chunks = await retrieve_context(refined_query, k=6)
        logger.info(f"Retrieved {len(retrieved_chunks)} chunks for context")
        
        # Step 5: Stream response from Speaker Agent and save to history
        full_response = ""
        async for chunk in stream_speaker_response(normalized_question, context, chat_history):
            yield chunk
            
            # Extract content from SSE data for saving
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    data = json.loads(chunk[6:])
                    if "content" in data:
                        full_response += data["content"]
                except Exception:
                    pass
        
        # OPTIMIZATION: Background save assistant response (non-blocking)
        if self.session_id and full_response:
            asyncio.create_task(save_session_message(self.session_id, "assistant", full_response))
            logger.debug(f"Saving assistant response ({len(full_response)} chars) to session {self.session_id} in background")


class SimpleChatFlow:
    """
    Simplified single-agent chat flow.
    
    Flow:
    1. Get session history
    2. Retrieve context from vector store
    3. Single unified agent handles routing + answering
    4. Save messages to session history
    
    No separate interpreter - the unified agent decides how to respond
    based on the message, context, and chat history.
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
    
    async def process_message(self, message: str):
        """
        Process a user message with a single unified agent.
        
        Args:
            message: The user's message
            
        Yields:
            SSE-formatted data chunks
        """
        logger.info(f"SimpleChatFlow processing (session: {self.session_id}): {message[:100]}...")
        
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
