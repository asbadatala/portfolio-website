# Portfolio Chatbot

An AI-powered chatbot for Ankit's portfolio website. Built with FastAPI, RAG (Retrieval Augmented Generation), and OpenAI, this chatbot provides intelligent answers about Ankit's work experience, projects, skills, and professional background.

## Features

- 🤖 **RAG-powered responses** - Uses vector search to retrieve relevant context from portfolio documents
- 💬 **Multi-turn conversations** - Maintains session history for contextual follow-up questions
- 🔍 **Query refinement** - LLM-powered query interpretation for better search results
- 📊 **Similarity-based retrieval** - Orders results by relevance (highest similarity first)
- 🎯 **Metadata filtering** - Prioritizes relevant document types (career, projects) based on query intent
- 📝 **Markdown support** - Renders formatted responses with proper markdown styling
- 🔐 **Session management** - Per-session chat history stored in Upstash Redis
- 🎤 **Voice flow placeholder** - Architecture ready for future voice integration

## Architecture

The project follows a clean, modular architecture:

```
website/
├── server.py              # Main FastAPI application
├── config.py              # Configuration & shared resources
├── requirements.txt       # Python dependencies
│
├── services/              # Core business logic
│   ├── session.py         # Redis session management
│   ├── retrieval.py       # RAG/vector search logic
│   └── llm.py             # OpenAI API interactions
│
├── flows/                 # Conversation flows
│   ├── chat.py            # Text-based chat flow
│   └── voice.py           # Voice flow (placeholder)
│
├── routes/                # API endpoints
│   ├── chat.py            # /api/chat, /api/session
│   └── voice.py           # /api/voice/* (placeholder)
│
└── prompts/               # Jinja2 templates
    ├── speaker_prompt.j2    # Speaker Agent prompt (generates responses)
    └── interpreter_prompt.j2 # Interpreter Agent prompt (routes messages)
```

## Prerequisites

- Python 3.11+
- Upstash Vector database (for RAG)
- Upstash Redis (for session history)
- OpenAI API key

## Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd portfolio/website
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the `website/` directory:
   ```env
   # OpenAI
   OPENAI_API_KEY=your_openai_api_key_here
   
   # Upstash Vector (for RAG)
   UPSTASH_VECTOR_REST_URL=your_upstash_vector_url
   UPSTASH_VECTOR_REST_TOKEN=your_upstash_vector_token
   UPSTASH_NAMESPACE=portfolio_rag_v2
   
   # Upstash Redis (for session history)
   UPSTASH_REDIS_REST_URL=your_upstash_redis_url
   UPSTASH_REDIS_REST_TOKEN=your_upstash_redis_token
   
   # Optional
   VOICE_ENABLED=false
   ```

5. **Run the server**
   ```bash
   python server.py
   ```
   
   Or with auto-reload (development):
   ```bash
   python server.py --reload
   ```
   
   The server will start on `http://localhost:3000`

## API Endpoints

### Chat Endpoints

- **`POST /api/session`** - Create a new chat session
  ```json
  Response: { "session_id": "uuid-string" }
  ```

- **`POST /api/chat`** - Send a chat message (streaming response)
  ```json
  Request: {
    "message": "Tell me about Ankit's work experience",
    "session_id": "uuid-string"  // optional
  }
  Response: Server-Sent Events (SSE) stream
  ```

### Config Endpoint

- **`GET /api/config`** - Get frontend configuration
  ```json
  Response: { "voiceEnabled": false }
  ```

### Voice Endpoints (Placeholder)

- **`POST /api/voice/start`** - Start voice call (not yet implemented)
- **`POST /api/voice/end`** - End voice call (not yet implemented)
- **`WebSocket /api/voice/stream`** - Voice streaming (not yet implemented)

## How It Works

### Two-Agent Architecture

The chatbot uses a two-agent system for efficient routing:

1. **Interpreter Agent** - Routes messages and decides if RAG is needed
2. **Speaker Agent** - Generates responses using RAG context

### Flow

1. **User sends a message** → Frontend sends to `/api/chat` with optional `session_id`
2. **Interpreter Agent** decides routing:
   - **Direct Response (early exit)**: Simple greetings, farewells, acknowledgments → respond immediately
   - **Needs Context**: Questions about Ankit → proceed to RAG
3. **RAG retrieval** (if needed) → Vector search finds relevant chunks from portfolio documents
4. **Speaker Agent** → Generates response using RAG context + chat history
5. **Streaming** → Response streams back to frontend via SSE
6. **History save** → User and assistant messages saved to Redis

### Early Exit Optimization

For simple conversational exchanges (greetings, thanks, etc.), the Interpreter Agent responds directly without hitting the RAG pipeline, reducing latency significantly.

## RAG Pipeline

The RAG (Retrieval Augmented Generation) system:

1. **Query Expansion** - Uses LLM interpreter to refine vague queries
2. **Vector Search** - Searches Upstash Vector database with similarity scoring
3. **Metadata Filtering** - Prioritizes relevant document types:
   - Work queries → `01_career_summary.md`
   - Project queries → `30_projects_and_extras.md`
4. **Similarity Sorting** - Orders chunks by similarity score (1.0 = most similar)
5. **Context Formatting** - Formats top-k chunks for LLM prompt

## Session Management

- Each chat session gets a unique UUID
- Session history stored in Upstash Redis
- TTL: 1 hour (configurable)
- Stores last 10 messages (5 user + 5 assistant)
- Used for conversation continuity and follow-up questions

## Development

### Project Structure

- **`services/`** - Reusable business logic (session, retrieval, LLM)
- **`flows/`** - Conversation orchestration (chat, voice)
- **`routes/`** - API endpoint definitions
- **`config.py`** - Centralized configuration

### Adding New Features

- **New service?** → Add to `services/`
- **New flow?** → Add to `flows/`
- **New endpoint?** → Add to `routes/`
- **New prompt?** → Add to `prompts/`

### Running Tests

```bash
# Add pytest to requirements.txt first
pytest
```

## Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `langchain-openai` - OpenAI embeddings
- `langchain-community` - Upstash Vector Store integration
- `upstash-redis` - Redis client for session history
- `upstash-vector` - Vector database client
- `jinja2` - Template engine for prompts
- `httpx` - Async HTTP client
- `python-dotenv` - Environment variable management

## Future Enhancements

- [ ] Voice flow implementation (WebSocket + speech-to-text/text-to-speech)
- [ ] Rate limiting
- [ ] Analytics and logging
- [ ] Multi-language support
- [ ] Admin dashboard


## Author

Ankit Badatala
