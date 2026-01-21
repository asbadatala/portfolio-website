"""
Routes module - contains API endpoint definitions.
"""
from .chat import router as chat_router
from .voice import router as voice_router

__all__ = ["chat_router", "voice_router"]
