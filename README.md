# Ankit's Portfolio — AI Assistant (RAG + Voice AI)

Live site: **[https://ankitsdesk.vercel.app/](https://ankitsdesk.vercel.app/)**

This repo contains the code for Ankit Badatala's portfolio site with a **streaming RAG chat assistant** and **real-time Voice AI** that answers questions using only the portfolio knowledge base.

## What this project demonstrates

- **Production-style RAG**: Upstash Vector search over curated portfolio documents
- **Strict grounding**: The assistant answers from retrieved context only
- **Streaming UX**: Server-Sent Events (SSE) to stream tokens to the UI
- **Session memory**: Redis-backed chat history (Upstash Redis) shared between chat and voice
- **Real-time Voice AI**: Streaming speech-to-text and text-to-speech via Deepgram
- **Live audio waveform**: Real-time visualization of both user speech and AI responses
- **Deployment on Vercel**: API runs as Python serverless functions

## Tech stack

- **Backend**: FastAPI + Uvicorn
- **LLM**: OpenAI Chat Completions (streaming)
- **Embeddings + Vector DB**: OpenAI embeddings + Upstash Vector (via LangChain)
- **Sessions**: Upstash Redis
- **Voice AI**: Deepgram Flux (STT) + Deepgram Aura (TTS)
- **Frontend**: Static HTML/CSS/JS with Web Audio API

## Features

### Chat Assistant
- RAG-powered responses grounded in portfolio documents
- Streaming responses with typing effect
- Session-based conversation history

### Voice AI
- **Speech-to-Text**: Deepgram Flux with turn detection for natural conversation flow
- **Text-to-Speech**: Deepgram Aura with streaming audio playback
- **Interruption support**: Stop the AI mid-sentence by speaking
- **Real waveform visualization**: Audio analyzer shows actual voice patterns (not simulated)
- **Client-side architecture**: Browser connects directly to Deepgram WebSockets (Vercel-compatible)

## Repo layout (website/)

```
website/
├── api/
│   └── index.py              # Vercel serverless function entry (FastAPI)
├── public/                   # Static site (served by Vercel)
│   ├── index.html            # Main portfolio page
│   ├── blogs.html            # Blog listing page
│   ├── blog/                 # Individual blog posts
│   │   └── building-voice-ai.html
│   ├── styles.css            # Global styles
│   ├── components/           # Reusable JS components
│   │   ├── social-links.js   # GitHub, LinkedIn, Spotify icons
│   │   └── back-button.js    # Navigation back button
│   └── objects/              # Images/videos
├── config.py                 # Env + shared clients (LLM, vector store, Redis)
├── routes/
│   ├── chat.py               # Chat API endpoint
│   ├── token.py              # Deepgram token endpoint
│   └── voice_chat.py         # Voice LLM processing endpoint
├── flows/
│   └── chat.py               # Chat orchestration
├── services/
│   ├── retrieval.py          # Vector search
│   ├── session.py            # Redis session management
│   └── llm.py                # LLM streaming
├── prompts/
│   ├── speaker_prompt.j2     # Chat system prompt
│   └── voice_prompt.j2       # Voice system prompt (conversational, first-person)
├── requirements.txt
├── vercel.json
└── server.py                 # Local dev server (serves `public/` + API)
```

## Frontend Components

Reusable JavaScript components are in `public/components/`:

### social-links.js
Social media icons (GitHub, LinkedIn, Spotify). Edit this single file to update links across all pages.

```html
<!-- Usage: Add to any page -->
<div class="social-links" id="social-links"></div>
<script src="/components/social-links.js"></script>
```

### back-button.js
Navigation back button with configurable destination.

```html
<!-- Usage: Set data-href for destination -->
<a class="back-button" id="back-button" data-href="/" data-label="Back to Home"></a>
<script src="/components/back-button.js"></script>
```

## Local development

From the repo root:

```bash
cd website
pip install -r requirements.txt
python server.py
```

Then open:
- **Frontend**: `http://localhost:3001/`
- **Health**: `http://localhost:3001/api/health`

> **Note**: Use `localhost` (not `127.0.0.1`) for microphone access in Chrome.

## Environment variables

Create `website/.env`:

```env
# OpenAI
OPENAI_API_KEY=...

# Upstash Vector
UPSTASH_VECTOR_REST_URL=...
UPSTASH_VECTOR_REST_TOKEN=...
UPSTASH_NAMESPACE=portfolio_rag_v2

# Upstash Redis (enables session history)
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...

# Deepgram (for Voice AI)
DEEPGRAM_API_KEY=...
DEEPGRAM_PROJECT_ID=...

# Security (optional — defaults to production domain)
# ALLOWED_ORIGINS=https://ankitsdesk.vercel.app
```

## API

All endpoints are rate-limited per IP using Upstash Redis.

- **`POST /api/session`**: Returns a session ID
- **`POST /api/chat`**: Streams an SSE response (`text/event-stream`) — 20 req/min
- **`GET /api/deepgram-token`**: Mints a short-lived Deepgram key (30s TTL) — 5 req/min
- **`POST /api/voice/chat`**: Streams LLM response for voice (plain text) — 20 req/min
- **`GET /api/health`**: Health check

## How it works

### Chat Flow
1. User sends a message
2. Backend retrieves **top-k relevant chunks** from Upstash Vector
3. LLM generates a response using retrieved context + chat history
4. Response is **streamed to the browser** over SSE

### Voice Flow
1. Browser captures microphone audio and streams to Deepgram Flux (STT)
2. Deepgram detects end-of-turn and returns transcript
3. Browser sends transcript to `/api/voice/chat` for LLM processing
4. LLM response streams back and is sent to Deepgram Aura (TTS)
5. Audio chunks are played with real-time waveform visualization

## Architecture Notes

- **Vercel-compatible**: Since Vercel serverless functions don't support WebSockets, the browser connects directly to Deepgram's WebSocket APIs. Vercel only handles short-lived HTTP requests (token minting, LLM calls).
- **Rate limit handling**: Built-in retry logic with exponential backoff for Deepgram API limits.
- **Shared session**: Chat and voice use the same Redis session, so context is preserved across modalities.

## Author

Ankit Badatala
