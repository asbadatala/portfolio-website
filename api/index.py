"""
Vercel serverless function entry point.
Exposes the FastAPI app for /api/* routes.
"""
import sys
import os

# Add parent directory to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from config import logger, VOICE_ENABLED
from routes.chat import router as chat_router
from routes.voice import router as voice_router

# Initialize FastAPI app for Vercel
app = FastAPI(
    title="Ankit's Portfolio Chatbot",
    description="AI assistant for Ankit's portfolio",
    version="1.0.0"
)

# Add CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(chat_router)
app.include_router(voice_router)

# Root redirect - FastAPI preset doesn't auto-serve static files at /
@app.get("/")
async def root():
    return RedirectResponse(url="/index.html")

# Config endpoint
@app.get("/api/config")
async def get_config():
    """Return frontend configuration."""
    return {
        "voiceEnabled": VOICE_ENABLED
    }

# Health check
@app.get("/api/health")
async def health():
    return {"status": "ok"}

# Debug endpoint to check routing
@app.get("/api/debug")
async def debug():
    return {"routes": [r.path for r in app.routes]}
