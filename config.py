"""
Configuration and shared resources for the portfolio chatbot.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores.upstash import UpstashVectorStore
from upstash_redis import Redis

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("portfolio")

# Disable httpx HTTP request logging
logging.getLogger("httpx").setLevel(logging.WARNING)

# --------------------------
# Environment Variables
# --------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").lower() == "true"
UPSTASH_NAMESPACE = os.getenv("UPSTASH_NAMESPACE", "portfolio_rag")
UPSTASH_REDIS_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

# --------------------------
# Jinja2 Templates
# --------------------------
template_dir = Path(__file__).parent / "prompts"
jinja_env = Environment(loader=FileSystemLoader(str(template_dir)))

# --------------------------
# Vector Store (RAG)
# --------------------------
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    dimensions=1536,
)

vector_store = UpstashVectorStore(
    embedding=embeddings,
    namespace=UPSTASH_NAMESPACE
)

# --------------------------
# Redis (Session History)
# --------------------------
redis_client = None
if UPSTASH_REDIS_URL and UPSTASH_REDIS_TOKEN:
    redis_client = Redis(url=UPSTASH_REDIS_URL, token=UPSTASH_REDIS_TOKEN)
    logger.info("Redis client initialized for session history")
else:
    logger.warning("Redis credentials not found - session history disabled")

# Session constants
SESSION_HISTORY_KEY_PREFIX = "chat_session:"
SESSION_TTL_SECONDS = 3600  # 1 hour session expiry
MAX_HISTORY_MESSAGES = 10  # Store last 10 messages (5 exchanges)
