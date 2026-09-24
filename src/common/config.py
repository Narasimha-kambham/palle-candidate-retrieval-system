"""
Centralized Configuration and Constants for PCRS (Palle Candidate Retrieval System)
"""

# ==============================================================================
# 1. Embedding & Vector Store Configuration
# ==============================================================================
EMBEDDING_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
CHUNK_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# ==============================================================================
# 2. LLM Model Providers & Models
# ==============================================================================
GEMINI_MODEL_NAME = "gemini-2.5-flash"
GEMINI_PROVIDER = "google_genai"

OPENAI_MODEL_NAME = "gpt-5.6-luna"
OPENAI_PROVIDER = "openai"

LLM_TEMPERATURE = 0

# ==============================================================================
# 3. Default Reranking & Scoring Weights
# ==============================================================================
DEFAULT_SEMANTIC_WEIGHT = 0.80
DEFAULT_EXACT_WEIGHT = 0.20

DEFAULT_WHOLE_RESUME_WEIGHT = 0.30
DEFAULT_BEST_CHUNK_WEIGHT = 0.40
DEFAULT_BEST_REQUIREMENT_WEIGHT = 0.30

DEFAULT_TOP_K = 20

# ==============================================================================
# 4. Server Logging Configuration
# ==============================================================================
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per log file
LOG_BACKUP_COUNT = 5              # Keep up to 5 rotated backup files
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"

# ==============================================================================
# 5. Network & Frontend Timeouts
# ==============================================================================
STREAMLIT_REQUEST_TIMEOUT = 600   # 10 minutes (in seconds)
