"""
RAG retrieval service.
Handles vector search, query expansion, and context formatting.
"""
import json
import httpx
from config import (
    logger,
    vector_store,
    jinja_env,
    OPENAI_API_KEY,
)


def build_section_path(metadata: dict) -> str:
    """
    Build section path from metadata headers (Header 1, Header 2, etc.)
    """
    headers = []
    for key in sorted(metadata.keys()):
        if key.lower().startswith("header"):
            val = metadata.get(key)
            if isinstance(val, str) and val.strip():
                headers.append(val.strip())
    return " > ".join(headers) if headers else ""


def expand_query(query: str) -> str:
    """
    Expand query to better match how content is written in the documents.
    Currently disabled - using LLM interpreter instead.
    """
    # Query expansion is now handled by refine_query_with_interpreter
    return query


async def interpret_user_query(user_query: str) -> dict:
    """
    Interpreter Agent: Routes user messages and determines if RAG is needed.
    
    Returns:
        dict with:
        - action: "direct_response" or "needs_context"
        - response: (if direct_response) The response to send directly
        - query: (if needs_context) The refined query for RAG search
    """
    # Default fallback: always go through RAG
    fallback_result = {"action": "needs_context", "query": user_query}
    
    try:
        # Render interpreter prompt
        template = jinja_env.get_template("interpreter_prompt.j2")
        interpreter_prompt = template.render()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENAI_API_KEY}"
                },
                json={
                    "model": "gpt-5-mini",
                    "messages": [
                        {"role": "system", "content": interpreter_prompt},
                        {"role": "user", "content": user_query}
                    ],
                    "max_completion_tokens": 400,
                    "reasoning_effort": "low",
                },
                timeout=10.0
            )
            
            if response.status_code != 200:
                error_text = await response.aread()
                error_msg = error_text.decode('utf-8') if error_text else "Unknown error"
                logger.warning(f"Interpreter API error ({response.status_code}): {error_msg}, falling back to RAG")
                return fallback_result
            
            result = response.json()
            logger.info(f"Interpreter API response structure: choices={len(result.get('choices', []))}")
            
            choices = result.get("choices", [])
            if not choices:
                logger.warning("No choices in interpreter response, falling back to RAG")
                return fallback_result
            
            message = choices[0].get("message", {})
            content = message.get("content", "").strip()
            finish_reason = choices[0].get("finish_reason", "")
            
            # Check if model used all tokens for reasoning (gpt-5-mini behavior)
            usage = result.get("usage", {})
            completion_details = usage.get("completion_tokens_details", {})
            reasoning_tokens = completion_details.get("reasoning_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            if not content:
                if reasoning_tokens > 0 and reasoning_tokens >= completion_tokens * 0.9:
                    logger.warning(f"Model used {reasoning_tokens}/{completion_tokens} tokens for reasoning with no output. Finish reason: {finish_reason}, falling back to RAG")
                else:
                    logger.warning(f"Empty content in interpreter response. Finish reason: {finish_reason}, falling back to RAG")
                return fallback_result
            
            # Parse JSON response
            try:
                # Try to extract JSON if it's wrapped in markdown code blocks
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                
                parsed = json.loads(content)
                action = parsed.get("action", "needs_context")
                
                if action == "direct_response":
                    direct_response = parsed.get("response", "")
                    if direct_response:
                        logger.info(f"Interpreter: DIRECT_RESPONSE for '{user_query[:50]}...'")
                        return {"action": "direct_response", "response": direct_response}
                    else:
                        logger.warning("Interpreter returned direct_response but no response text, falling back to RAG")
                        return fallback_result
                else:
                    # needs_context
                    refined_query = parsed.get("query", user_query)
                    logger.info(f"Interpreter: NEEDS_CONTEXT - Query refined: '{user_query}' -> '{refined_query}'")
                    return {"action": "needs_context", "query": refined_query}
                    
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse interpreter JSON: {content[:200]}, error: {e}, falling back to RAG")
                return fallback_result
                
    except Exception as e:
        logger.warning(f"Error in interpreter: {e}, falling back to RAG")
        return fallback_result


async def retrieve_context(query: str, k: int = 5) -> tuple[str, list]:
    """
    Retrieve relevant context from Upstash vector store based on user query.
    Uses query expansion and metadata filtering for better results.
    Returns tuple of (formatted context string, list of retrieved chunks for logging).
    """
    try:
        logger.info(f"Retrieving context for query: {query}...")
        
        # Expand query for better matching
        expanded_query = expand_query(query)
        logger.info(f"Expanded query: {expanded_query}")
        
        # Determine if we should filter by metadata based on query type
        query_lower = query.lower()
        
        # Try to get results with scores for ordering
        # NOTE: similarity_search_with_score returns (doc, score) where score is SIMILARITY (1.0 = identical, 0.0 = no match)
        # We sort descending so most similar chunks (score closest to 1.0) come first
        try:
            docs_with_scores = vector_store.similarity_search_with_score(expanded_query, k=k*3)
        except (AttributeError, TypeError):
            logger.warning("similarity_search_with_score not available, using regular search")
            docs_with_scores = [(doc, 1.0) for doc in vector_store.similarity_search(expanded_query, k=k*3)]
        
        if not docs_with_scores:
            logger.info("No chunks retrieved from vector store")
            return "", []
        
        # For work-related queries, prioritize career_summary.md
        if any(word in query_lower for word in ["work", "job", "company", "employer", "career", "experience", "worked", "employment"]):
            career_chunks_with_scores = [
                (doc, score) for doc, score in docs_with_scores
                if doc.metadata.get("file_name") == "01_career_summary.md"
            ]
            other_chunks_with_scores = [
                (doc, score) for doc, score in docs_with_scores
                if doc.metadata.get("file_name") != "01_career_summary.md"
            ]
            
            career_chunks_with_scores.sort(key=lambda x: x[1], reverse=True)
            other_chunks_with_scores.sort(key=lambda x: x[1], reverse=True)
            
            selected = career_chunks_with_scores[:k] + other_chunks_with_scores[:max(0, k - len(career_chunks_with_scores))]
            selected = selected[:k]
            selected.sort(key=lambda x: x[1], reverse=True)
            
            if career_chunks_with_scores:
                logger.info(f"Prioritized {len(career_chunks_with_scores)} chunks from career_summary.md")
        
        # For project-related queries, prioritize projects_and_extras.md
        elif any(word in query_lower for word in ["project", "publication"]):
            project_chunks_with_scores = [
                (doc, score) for doc, score in docs_with_scores
                if doc.metadata.get("file_name") == "30_projects_and_extras.md"
            ]
            other_chunks_with_scores = [
                (doc, score) for doc, score in docs_with_scores
                if doc.metadata.get("file_name") != "30_projects_and_extras.md"
            ]
            
            project_chunks_with_scores.sort(key=lambda x: x[1], reverse=True)
            other_chunks_with_scores.sort(key=lambda x: x[1], reverse=True)
            
            selected = project_chunks_with_scores[:k] + other_chunks_with_scores[:max(0, k - len(project_chunks_with_scores))]
            selected = selected[:k]
            selected.sort(key=lambda x: x[1], reverse=True)
            
            if project_chunks_with_scores:
                logger.info(f"Prioritized {len(project_chunks_with_scores)} chunks from 30_projects_and_extras.md")
        
        else:
            selected = sorted(docs_with_scores, key=lambda x: x[1], reverse=True)[:k]
        
        # Extract chunks and scores
        chunks = [doc for doc, score in selected]
        scores = [score for doc, score in selected]
        
        logger.info(f"Retrieved {len(chunks)} chunks from vector store (scores: {[f'{s:.4f}' for s in scores]})")
        
        # Format the retrieved chunks as context
        context_parts = []
        retrieved_chunks = []
        
        for i, (chunk, score) in enumerate(zip(chunks, scores), 1):
            content = chunk.page_content.strip()
            metadata = chunk.metadata or {}
            file_name = metadata.get("file_name", "Unknown")
            section_path = build_section_path(metadata)
            
            chunk_info = {
                "index": i,
                "file_name": file_name,
                "section_path": section_path,
                "similarity_score": float(score),
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
                "content_length": len(content),
                "metadata": metadata
            }
            retrieved_chunks.append(chunk_info)
            
            logger.info(f"Chunk {i}: {file_name} | {section_path} | score: {score:.4f}")
            
            if section_path:
                context_parts.append(f"[{i}] From {file_name} - {section_path}:\n{content}")
            else:
                context_parts.append(f"[{i}] From {file_name}:\n{content}")
        
        formatted_context = "\n\n".join(context_parts)
        
        return formatted_context, retrieved_chunks
    except Exception as e:
        logger.error(f"Error retrieving context: {e}", exc_info=True)
        return "", []
