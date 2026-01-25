"""
LLM service for OpenAI API interactions.
Handles streaming responses and prompt rendering.
"""
import json
import httpx
from config import logger, jinja_env, OPENAI_API_KEY


async def stream_unified_agent(message: str, context: str = "", chat_history: str = ""):
    """
    Stream response from the Unified Agent (single agent that handles routing + answering).
    Uses new_speaker_prompt.j2 template.
    Yields SSE-formatted data chunks.
    """
    # Render system prompt from Jinja template
    template = jinja_env.get_template("new_speaker_prompt.j2")
    system_content = template.render(context=context, chat_history=chat_history)
    
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            },
            json={
                "model": "gpt-4.1-mini",
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": message}
                ],
                "max_completion_tokens": 800,
                "stream": True
            },
            timeout=60.0
        ) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                error_msg = error_text.decode('utf-8') if error_text else "Unknown error"
                logger.error(f"OpenAI API error ({response.status_code}): {error_msg}")
                yield f"data: {json.dumps({'error': f'API request failed: {error_msg}'})}\n\n"
                return

            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                    
                if line.startswith("data: "):
                    data = line[6:].strip()
                    if data == "[DONE]":
                        yield "data: [DONE]\n\n"
                        continue
                    
                    try:
                        parsed = json.loads(data)
                        choices = parsed.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Error processing stream: {e}", exc_info=True)


async def stream_speaker_response(message: str, context: str = "", chat_history: str = ""):
    """
    Stream response from the Speaker Agent with RAG context and chat history.
    Yields SSE-formatted data chunks.
    """
    # Render system prompt from Jinja template
    template = jinja_env.get_template("speaker_prompt.j2")
    system_content = template.render(context=context, chat_history=chat_history)
    
    # Log context size (without full content to avoid spam)
    estimated_tokens = len(system_content) // 4 + len(message) // 4
    logger.info(f"Context size: {len(system_content)} chars (~{estimated_tokens} tokens)")
    
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            },
            json={
                "model": "gpt-4.1-mini",
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": message}
                ],
                "max_completion_tokens": 1200,
                "stream": True
            },
            timeout=60.0
        ) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                error_msg = error_text.decode('utf-8') if error_text else "Unknown error"
                logger.error(f"OpenAI API error ({response.status_code}): {error_msg}")
                yield f"data: {json.dumps({'error': f'API request failed: {error_msg}'})}\n\n"
                return

            content_chunks_yielded = 0
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                    
                if line.startswith("data: "):
                    data = line[6:].strip()
                    if data == "[DONE]":
                        yield "data: [DONE]\n\n"
                        continue
                    
                    try:
                        parsed = json.loads(data)
                        choices = parsed.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            
                        if content:
                            content_chunks_yielded += 1
                            yield f"data: {json.dumps({'content': content})}\n\n"
                            
                        # Check for early termination (only log if problematic)
                        finish_reason = choices[0].get("finish_reason")
                        if finish_reason == "length" and content_chunks_yielded < 10:
                            logger.warning(f"Stream finished early ({content_chunks_yielded} chunks). System prompt may be too long.")
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Error processing stream: {e}", exc_info=True)
                        pass
