import sys
import os

# Add repo root to path so we can import config/routes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from routes.chat import router as chat_router
from routes.token import router as token_router
from routes.voice_chat import router as voice_chat_router

app = FastAPI(
    title="Ankit's Portfolio Chatbot",
    description="AI assistant for Ankit's portfolio",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP routes for Vercel serverless
app.include_router(chat_router, prefix="/api")
app.include_router(token_router, prefix="/api")
app.include_router(voice_chat_router, prefix="/api")

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/debug")
async def debug():
    return {"routes": [r.path for r in app.routes]}
