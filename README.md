# AI-Powered Portfolio with Chatbot + Voice Assistant
A portfolio website with two AI interfaces: a **streaming RAG chatbot** and a **real-time voice assistant** with sub second latency. Both can answer questions about my experience using only a personally curated knowledge base to avoid hallucinations.

Learn about me through natural conversation, not skimming a PDF.

**Live:** [ankitsdesk.vercel.app](https://ankitsdesk.vercel.app/)
Demo (2/6/2026):


## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, deployed as Vercel serverless functions |
| LLM | OpenAI GPT-4o-mini (streaming completions) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims) |
| Vector DB | Upstash Vector via LangChain |
| Sessions | Upstash Redis (shared between chat and voice) |
| Voice STT | Deepgram Flux (WebSocket, client-side) |
| Voice TTS | Deepgram Aura (WebSocket, client-side) |
| Frontend | Vanilla HTML/CSS/JS, Web Audio API, AnalyserNode |

## Architecture

```
Browser                          Vercel (Serverless)              External APIs
┌──────────────────┐             ┌──────────────────┐             ┌─────────────────┐
│                  │   POST      │                  │   Embed +   │                 │
│  Chat UI ────────┼────────────>│  /api/chat       │───Query────>│  Upstash Vector │
│  (SSE stream)    │<────────────│  (RAG + LLM)     │             │                 │
│                  │   SSE       │                  │   Stream    │  OpenAI GPT-4o  │
│                  │             │                  │────────────>│  (completions)  │
├──────────────────┤             ├──────────────────┤             ├─────────────────┤
│                  │   GET       │                  │   Mint key  │                 │
│  Voice UI ───────┼────────────>│  /api/token      │────────────>│  Deepgram API   │
│  (Web Audio API) │<────────────│  (30s TTL key)   │             │  (key creation) │
│                  │             ├──────────────────┤             ├─────────────────┤
│       ┌──────────┤   WSS      │                  │             │                 │
│       │ Mic ─────┼────────────┼──────────────────┼────────────>│  Deepgram Flux  │
│       │          │<───────────┼──────────────────┼─────────────│  (STT)          │
│       └──────────┤  transcript│                  │             ├─────────────────┤
│       ┌──────────┤   POST     │                  │             │                 │
│       │ Speaker──┼────────────┤  /api/voice/chat │────────────>│  OpenAI GPT-4o  │
│       │          │<───────────┤  (RAG + LLM)     │   Stream    │  (completions)  │
│       └──────────┤   WSS      │                  │             ├─────────────────┤
│       ┌──────────┼────────────┼──────────────────┼────────────>│  Deepgram Aura  │
│       │ Audio out│<───────────┼──────────────────┼─────────────│  (TTS)          │
│       └──────────┤            │                  │             │                 │
│  Waveform visual │            │  Rate Limiter    │             │  Upstash Redis  │
│  (AnalyserNode)  │            │  (per-IP, Redis) │<───────────>│  (sessions +    │
│                  │            │                  │             │   rate limits)  │
└──────────────────┘             └──────────────────┘             └─────────────────┘
```

**Key constraint**: Vercel serverless functions don't support WebSockets. The browser connects directly to Deepgram's WebSocket APIs using short-lived keys minted by the server. Vercel only handles stateless HTTP (token minting, LLM streaming).

## Engineering Decisions

### RAG: Chunking for Accuracy

Documents are split at `#` and `##` header boundaries only (not `###`), keeping entire project descriptions in single chunks. This prevents the LLM from conflating details across projects — e.g., attributing one project's team size to another.

### Voice: Client-Side WebSocket Architecture

Since Vercel can't hold WebSocket connections, the browser owns the Deepgram connections directly. The server's only role is minting a 30-second ephemeral API key per call. This keeps the architecture serverless-compatible while maintaining low-latency audio streaming.

### Security: Defense in Depth

| Protection | Implementation |
|---|---|
| API key exposure | Server mints 30s TTL Deepgram keys; real key never reaches the browser |
| Abuse prevention | Redis-backed per-IP rate limiting (token: 5/min, chat: 20/min, voice: 20/min) |
| Cross-origin | CORS locked to production domain (`ankitsdesk.vercel.app`) |
| Vercel proxy | IP extraction reads `x-real-ip` so rate limits apply to the real client, not Vercel's internal proxy |
| Fail-open | If Redis is unavailable, rate limiter degrades gracefully (allows requests) |

### Voice: Interruption and State Management

Users can interrupt the AI mid-sentence. When speech is detected during playback, the audio queue is flushed, TTS is stopped, and the new transcript is processed immediately. A waveform visualizer driven by `AnalyserNode` reflects the actual pipeline state (listening, processing, speaking) with a 15-second safety timeout to recover from stuck states.

## API Endpoints

All endpoints are rate-limited per IP via Upstash Redis.

| Endpoint | Method | Description | Rate Limit |
|---|---|---|---|
| `/api/session` | POST | Create a new chat session | -- |
| `/api/chat` | POST | Stream a RAG-augmented LLM response (SSE) | 20/min |
| `/api/deepgram-token` | GET | Mint a short-lived Deepgram key (30s TTL) | 5/min |
| `/api/voice/chat` | POST | Stream LLM response for voice (plain text) | 20/min |
| `/api/health` | GET | Health check | -- |

## Project Structure

```
website/
├── api/index.py                 # Vercel serverless entry point
├── server.py                    # Local dev server (static files + API)
├── config.py                    # Environment, clients, shared state
├── routes/
│   ├── chat.py                  # POST /api/chat — streaming RAG chat
│   ├── voice_chat.py            # POST /api/voice/chat — voice LLM
│   └── token.py                 # GET /api/deepgram-token — ephemeral keys
├── flows/
│   └── chat.py                  # Chat orchestration (retrieval + LLM + session)
├── services/
│   ├── retrieval.py             # Upstash Vector similarity search
│   ├── session.py               # Redis session read/write
│   ├── rate_limit.py            # Per-IP rate limiter (Redis-backed)
│   └── llm.py                   # OpenAI streaming wrapper
├── prompts/
│   ├── speaker_prompt.j2        # Chat system prompt (Jinja2)
│   └── voice_prompt.j2          # Voice system prompt (concise, first-person)
├── public/                      # Static frontend
│   ├── index.html               # Main page (chat + voice UI)
│   ├── projects.html            # Projects showcase
│   ├── blogs.html               # Blog listing
│   ├── blog/                    # Blog posts
│   ├── styles.css               # Global styles
│   └── components/              # Reusable JS (social links, back button)
├── data_ingestion/
│   ├── build_embeddings_upstash.py  # Markdown chunking + embedding pipeline
│   └── documents/               # Source markdown files
├── requirements.txt
└── vercel.json
```

## Setup

```bash
cd website
pip install -r requirements.txt
python server.py
# → http://localhost:3001
```

### Environment Variables

Create `website/.env`:

```env
OPENAI_API_KEY=...
UPSTASH_VECTOR_REST_URL=...
UPSTASH_VECTOR_REST_TOKEN=...
UPSTASH_NAMESPACE=portfolio_rag_v2
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
DEEPGRAM_API_KEY=...              # Admin role required (keys:write scope)
DEEPGRAM_PROJECT_ID=...           # Deepgram Console → Settings → Project
# ALLOWED_ORIGINS=https://ankitsdesk.vercel.app  # Defaults to production domain
```

> The Deepgram API key needs the `keys:write` scope to mint temporary keys. See [Deepgram roles documentation](https://developers.deepgram.com/guides/deep-dives/working-with-roles).

> Use `localhost` (not `127.0.0.1`) for microphone access in Chrome.

## Author

Ankit Badatala
