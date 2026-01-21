"""
Portfolio Chatbot Server

Main FastAPI application that ties together all modules.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import logger, VOICE_ENABLED
from routes.chat import router as chat_router
from routes.voice import router as voice_router

# Initialize FastAPI app
app = FastAPI(
    title="Ankit's Portfolio Chatbot",
    description="AI assistant for Ankit's portfolio",
    version="1.0.0"
)

# --------------------------
# Include Routers
# --------------------------
app.include_router(chat_router)
app.include_router(voice_router)

# --------------------------
# Config Endpoint
# --------------------------
@app.get("/api/config")
async def get_config():
    """Return frontend configuration."""
    return {
        "voiceEnabled": VOICE_ENABLED
    }

# --------------------------
# Static File Serving
# --------------------------
@app.get("/")
async def root():
    """Serve index.html at root."""
    return FileResponse("index.html")

# Serve static files (must be after specific routes)
app.mount("/", StaticFiles(directory="."), name="static")

# --------------------------
# Main Entry Point
# --------------------------
if __name__ == "__main__":
    import uvicorn
    import sys
    
    logger.info("Starting Portfolio Chatbot Server...")
    
    # Use import string format for reload to work properly
    if "--reload" in sys.argv or len(sys.argv) == 1:
        # Run with reload enabled (development mode)
        uvicorn.run(
            "server:app",  # Import string format required for reload
            host="0.0.0.0",
            port=3000,
            reload=True,
            reload_includes=["*.py", "*.j2"],
            reload_dirs=[".", "services", "flows", "routes", "prompts"],
        )
    else:
        # Run without reload (production mode)
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=3000,
        )
