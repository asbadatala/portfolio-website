"""
Portfolio Chatbot Server

Main FastAPI application that ties together all modules.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import logger
from routes.chat import router as chat_router
from routes.voice import router as voice_router

# Initialize FastAPI app
app = FastAPI(
    title="Ankit's Portfolio Chatbot",
    description="AI assistant for Ankit's portfolio",
    version="1.0.0"
)

# --------------------------
# Include Routers (with /api prefix for local dev, matches Vercel behavior)
# --------------------------
app.include_router(chat_router, prefix="/api")
app.include_router(voice_router, prefix="/api")

# --------------------------
# Health Check
# --------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok"}

# --------------------------
# Static File Serving
# --------------------------
@app.get("/")
async def root():
    """Serve index.html at root."""
    return FileResponse("public/index.html")

# Serve static files from public folder
app.mount("/", StaticFiles(directory="public"), name="static")

# --------------------------
# Main Entry Point
# --------------------------
if __name__ == "__main__":
    import uvicorn
    import sys
    
    logger.info("Starting Portfolio Chatbot Server...")
    logger.info("Access at: http://localhost:3001 (use localhost for microphone access)")
    
    # Use import string format for reload to work properly
    if "--reload" in sys.argv or len(sys.argv) == 1:
        # Run with reload enabled (development mode)
        uvicorn.run(
            "server:app",  # Import string format required for reload
            host="0.0.0.0",
            port=3001,
            reload=True,
            reload_includes=["*.py", "*.j2"],
            reload_dirs=[".", "services", "flows", "routes", "prompts"],
        )
    else:
        # Run without reload (production mode)
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=3001,
        )
