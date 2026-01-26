# Ankit’s Portfolio — AI Assistant (RAG + Streaming)

Live site: **[https://ankitsdesk.vercel.app/](https://ankitsdesk.vercel.app/)**

This repo contains the code for Ankit Badatala’s portfolio site + a **streaming, retrieval-augmented (RAG) chat assistant** that answers questions using only the portfolio knowledge base.

## What this project demonstrates

- **Production-style RAG**: Upstash Vector search over curated portfolio documents
- **Strict grounding**: The assistant is instructed to answer from retrieved context only
- **Streaming UX**: Server-Sent Events (SSE) to stream tokens to the UI
- **Session memory (optional)**: Redis-backed chat history (Upstash Redis)
- **Deployment on Vercel**: API runs as a Python serverless function

## Tech stack

- **Backend**: FastAPI + Uvicorn
- **LLM**: OpenAI Chat Completions (streaming)
- **Embeddings + Vector DB**: OpenAI embeddings + Upstash Vector (via LangChain)
- **Sessions**: Upstash Redis (optional)
- **Frontend**: Static HTML/CSS/JS (served from `public/`)

## Repo layout (website/)

```
website/
├── api/
│   └── index.py              # Vercel serverless function entry (FastAPI)
├── public/                   # Static site (served by Vercel)
│   ├── index.html
│   ├── styles.css
│   └── objects/              # Images/videos
├── config.py                 # Env + shared clients (LLM, vector store, Redis)
├── routes/                   # API endpoints (chat + voice placeholder)
├── flows/                    # Chat orchestration
├── services/                 # Retrieval, session, and LLM streaming
├── prompts/
│   └── speaker_prompt.j2     # Unified agent system prompt
├── requirements.txt
├── vercel.json
└── server.py                 # Local dev server (serves `public/` + API)
```

## Local development

From the repo root:

```bash
cd website
pip install -r requirements.txt
python server.py
```

Then open:
- **Frontend**: `http://localhost:3000/`
- **Health**: `http://localhost:3000/api/health`

## Environment variables

Create `website/.env`:

```env
# OpenAI
OPENAI_API_KEY=...

# Upstash Vector
UPSTASH_VECTOR_REST_URL=...
UPSTASH_VECTOR_REST_TOKEN=...
UPSTASH_NAMESPACE=portfolio_rag

# Upstash Redis (optional, enables session history)
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
```

## API

- **`POST /api/session`**: returns a session id
- **`POST /api/chat`**: streams an SSE response (`text/event-stream`)
- **`GET /api/health`**: health check

## How chat works (high level)

1. The user sends a message.
2. The backend retrieves **top-k relevant chunks** from Upstash Vector.
3. A **single unified agent** generates a response using the retrieved context + recent chat history.
4. The response is **streamed to the browser** over SSE.

## Notes

- The voice endpoints are currently **placeholders** (not yet implemented).
- This project is intentionally optimized for recruiter-friendly, grounded answers about Ankit’s background (and avoids “outside knowledge” when the data isn’t present).

## Author

Ankit Badatala
