import sys
import os

# Add repo root to path so we can import config/routes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import VOICE_ENABLED
from routes.chat import router as chat_router
from routes.voice import router as voice_router

app = FastAPI(
    title="Ankit's Portfolio Chatbot",
    description="AI assistant for Ankit's portfolio",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(voice_router)

@app.get("/config")
async def get_config():
    return {"voiceEnabled": VOICE_ENABLED}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/debug")
async def debug():
    return {"routes": [r.path for r in app.routes]}