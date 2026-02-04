"""
Routes module - contains API endpoint definitions.
"""
from .chat import router as chat_router
from .token import router as token_router
from .voice_chat import router as voice_chat_router

__all__ = ["chat_router", "token_router", "voice_chat_router"]
