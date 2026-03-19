import os
import re
from pathlib import Path


def get_env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean environment variables safely."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

# Auto-load .env file if it exists (before reading environment variables)
# This ensures .env file is loaded even if load_dotenv wasn't called yet
try:
    from dotenv import load_dotenv
    # Try to find .env file in backend directory
    # This file is in backend/config/settings.py, so .env should be in backend/.env
    current_file = Path(__file__)
    backend_dir = current_file.parent.parent  # Go up from config/ to backend/
    env_file = backend_dir / '.env'
    if env_file.exists():
        load_dotenv(env_file, override=True)
except ImportError:
    # python-dotenv not installed, skip
    pass
except Exception:
    # Ignore errors during .env loading
    pass

# LLM API Configuration
# OpenAI API
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API key

# Proxy Configuration (for regions where OpenAI is blocked)
OPENAI_PROXY_URL = os.getenv("OPENAI_PROXY_URL", "http://127.0.0.1:7890")  # Clash default proxy
OPENAI_USE_PROXY = os.getenv("OPENAI_USE_PROXY", "true").lower() == "true"  # Enable proxy by default

# Default to OpenAI API
LLM_API_KEY = OPENAI_API_KEY
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # "openai"

# backend directory absolute path
BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/

# Embedding Configuration
# Cloud Run uses RAG_STORAGE_BACKEND=gcs; when gcs, default to openai (Ollama not available in cloud)
_default_embed = "openai" if os.getenv("RAG_STORAGE_BACKEND", "").strip().lower() == "gcs" else "ollama"
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", _default_embed)  # "openai" or "ollama"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")  # 推荐的 embedding 模型
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")  # default chat model for Ollama
# Batch size for Ollama /api/embed (input array). Larger = fewer requests; >16 may reduce quality.
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))

# RAG Knowledge Base: max chunks per file (over limit triggers adaptive larger chunk size so full file is indexed)
MAX_RAG_CHUNKS = int(os.getenv("MAX_RAG_CHUNKS", "5000"))

# RAG file storage backend: "local" (default) or "gcs"
# Use "gcs" on Cloud Run for persistent storage; "local" for development
RAG_STORAGE_BACKEND = os.getenv("RAG_STORAGE_BACKEND", "local").strip().lower()
RAG_GCS_BUCKET = os.getenv("RAG_GCS_BUCKET", "").strip()

# Feature flags (default OFF for backward compatibility).
# These are scaffold flags for phased rollout in architecture upgrade.
FEATURE_TEXT_NORMALIZATION = get_env_bool("FEATURE_TEXT_NORMALIZATION", False)
FEATURE_LANGUAGE_DETECTION_V2 = get_env_bool("FEATURE_LANGUAGE_DETECTION_V2", False)
FEATURE_HYBRID_FALLBACK = get_env_bool("FEATURE_HYBRID_FALLBACK", True)
FEATURE_AGENT_ROUTER = get_env_bool("FEATURE_AGENT_ROUTER", False)
FEATURE_TREEID_ENHANCE = get_env_bool("FEATURE_TREEID_ENHANCE", True)
FEATURE_RAG_CONTEXT_BUILDER = get_env_bool("FEATURE_RAG_CONTEXT_BUILDER", True)
FEATURE_DYNAMIC_KB = get_env_bool("FEATURE_DYNAMIC_KB", True)
FEATURE_RATE_LIMIT = get_env_bool("FEATURE_RATE_LIMIT", False)
FEATURE_METRICS = get_env_bool("FEATURE_METRICS", True)

# RAGAS evaluation settings
RAGAS_ENABLED = get_env_bool("RAGAS_ENABLED", False)
RAGAS_TIMEOUT_SECONDS = int(os.getenv("RAGAS_TIMEOUT_SECONDS", "8"))
RAGAS_LLM_MODEL = os.getenv("RAGAS_LLM_MODEL", "gpt-4o")  # LLM used as judge

# Runtime and infrastructure settings for PostgreSQL/pgvector rollout.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/srr")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")

# External public data APIs
LANDSD_WFS_URL = os.getenv(
    "LANDSD_WFS_URL",
    "https://portal.csdi.gov.hk/server/services/common/landsd_rcd_1637220975523_8411/MapServer/WFSServer",
)
CEDD_WFS_URL = os.getenv(
    "CEDD_WFS_URL",
    "https://portal.csdi.gov.hk/server/services/common/cedd_rcd_1636517655915_91216/MapServer/WFSServer",
)
HKO_API_URL = os.getenv(
    "HKO_API_URL",
    "https://data.weather.gov.hk/weatherAPI/opendata/weather.php",
)
EXTERNAL_API_TIMEOUT = int(os.getenv("EXTERNAL_API_TIMEOUT", "5"))
EXTERNAL_API_ENABLED = get_env_bool("EXTERNAL_API_ENABLED", True)
GEOINFO_API_URL = os.getenv(
    "GEOINFO_API_URL",
    "https://www.map.gov.hk/gs/api/v1/locationSearch",
)

# Server: keep-alive timeout (seconds) so long-running clients/proxies don't get dropped
UVICORN_TIMEOUT_KEEP_ALIVE = int(os.getenv("UVICORN_TIMEOUT_KEEP_ALIVE", "120"))

# Security mode: fail fast on unsafe defaults
SECURE_MODE = os.getenv("SECURE_MODE", "true").lower() == "true"


def _is_weak_jwt_secret(secret: str) -> bool:
    lowered = (secret or "").lower()
    if len(secret or "") < 32:
        return True
    if re.fullmatch(r"[A-Za-z0-9]+", secret or "") and len(secret or "") < 40:
        return True
    weak_markers = ("please-change", "changeme", "default", "secret")
    return any(marker in lowered for marker in weak_markers)


def ensure_security_config() -> None:
    """Validate required security-related settings."""
    if not SECURE_MODE:
        return
    jwt_secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET_KEY is required")
    if _is_weak_jwt_secret(jwt_secret):
        raise RuntimeError("JWT_SECRET_KEY is too weak; use at least 32 high-entropy characters")