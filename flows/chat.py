"""
Chat flow - handles text-based conversation logic.
Orchestrates routing, retrieval, LLM calls, and session management for chat.
"""
import json
import asyncio
from config import logger
from services.session import get_session_history, save_session_message, format_chat_history
from services.retrieval import retrieve_context, interpret_user_query
from services.llm import stream_speaker_response


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
    
    def __init__(self, session_id: str = None):
        self.session_id = session_id
    
    async def process_message(self, message: str):
        """
        Process a user message and return a streaming response generator.
        
        Args:
            message: The user's message
            
        Yields:
            SSE-formatted data chunks
        """
        logger.info(f"Chat flow processing (session: {self.session_id}): {message[:100]}...")
        
        # Step 1: Get chat history for context
        history = await get_session_history(self.session_id) if self.session_id else []
        chat_history = format_chat_history(history, max_exchanges=5)
        
        if chat_history:
            logger.info(f"Including {len(history)} messages from session history")
        
        # Step 2: Save user message to history
        if self.session_id:
            await save_session_message(self.session_id, "user", message)
        
        # Step 3: Interpreter Agent decides routing
        interpreter_result = await interpret_user_query(message)
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
            
            # Save assistant response to history
            if self.session_id and direct_response:
                await save_session_message(self.session_id, "assistant", direct_response)
            return
        
        # Step 3b: Needs context - go through RAG
        refined_query = interpreter_result.get("query", message)
        
        # Step 4: Retrieve relevant context from vector store
        context, retrieved_chunks = await retrieve_context(refined_query, k=5)
        logger.info(f"Retrieved {len(retrieved_chunks)} chunks for context")
        
        # Step 5: Stream response from Speaker Agent and save to history
        full_response = ""
        async for chunk in stream_speaker_response(message, context, chat_history):
            yield chunk
            
            # Extract content from SSE data for saving
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    data = json.loads(chunk[6:])
                    if "content" in data:
                        full_response += data["content"]
                except:
                    pass
        
        # Step 6: Save assistant response to history
        if self.session_id and full_response:
            await save_session_message(self.session_id, "assistant", full_response)
            logger.debug(f"Saved assistant response ({len(full_response)} chars) to session {self.session_id}")
