"""
RAG retrieval service.
Handles vector search and context formatting.
"""
from config import logger, vector_store


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


async def retrieve_context(query: str, k: int = 6) -> tuple[str, list]:
    """
    Retrieve relevant context from Upstash vector store based on user query.
    Returns tuple of (formatted context string, list of retrieved chunks for logging).
    """
    try:
        logger.info(f"Retrieving context for query: {query[:100]}...")
        
        # Get results with scores for ordering
        # NOTE: similarity_search_with_score returns (doc, score) where score is SIMILARITY (1.0 = identical, 0.0 = no match)
        try:
            docs_with_scores = vector_store.similarity_search_with_score(query, k=k*2)
        except (AttributeError, TypeError):
            logger.warning("similarity_search_with_score not available, using regular search")
            docs_with_scores = [(doc, 1.0) for doc in vector_store.similarity_search(query, k=k*2)]
        
        if not docs_with_scores:
            logger.info("No chunks retrieved from vector store")
            return "", []
        
        # Sort by score descending (most similar first) and take top k
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
            
            # Log chunk with content (truncate if too long)
            content_preview = content[:500] + "..." if len(content) > 500 else content
            logger.info(f"Chunk {i}: {file_name} | {section_path} | score: {score:.4f}\nContent: {content_preview}")
            
            if section_path:
                context_parts.append(f"[{i}] From {file_name} - {section_path}:\n{content}")
            else:
                context_parts.append(f"[{i}] From {file_name}:\n{content}")
        
        formatted_context = "\n\n".join(context_parts)
        
        return formatted_context, retrieved_chunks
    except Exception as e:
        logger.error(f"Error retrieving context: {e}", exc_info=True)
        return "", []
