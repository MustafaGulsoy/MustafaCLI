"""
Constants - Application-wide Constants
=======================================

Centralized constant definitions to avoid magic numbers and strings.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

# File and Content Limits
MAX_FILE_SIZE_CHARS = 100_000  # 100KB text equivalent
MAX_OUTPUT_CHARS = 100_000  # Maximum tool output size
MAX_DIR_ENTRIES = 500  # Maximum directory listing entries
MAX_DIR_DEPTH = 2  # Maximum depth for directory traversal

# Agent Configuration
DEFAULT_MODEL = "qwen2.5-coder:32b"
DEFAULT_TEMPERATURE = 0.0  # Deterministic for coding
DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_ITERATIONS = 100  # Prevent infinite loops
DEFAULT_MAX_CONSECUTIVE_TOOL_CALLS = 20  # Circuit breaker
DEFAULT_THINKING_BUDGET = 10_000

# Context Management
DEFAULT_MAX_CONTEXT_TOKENS = 32_000  # Model context window
DEFAULT_CONTEXT_RESERVE_TOKENS = 4_000  # Reserved for response
DEFAULT_COMPACTION_THRESHOLD = 0.8  # 80% full triggers compaction
DEFAULT_KEEP_RECENT_MESSAGES = 10  # Messages to keep after compaction

# Timeouts (seconds)
DEFAULT_TOOL_TIMEOUT = 300  # 5 minutes
DEFAULT_BASH_TIMEOUT = 120  # 2 minutes
DEFAULT_HTTP_TIMEOUT = 300  # 5 minutes
DEFAULT_MODEL_TIMEOUT = 300  # 5 minutes

# Token Estimation
CHARS_PER_TOKEN = 4.0  # Average for English text
MESSAGE_OVERHEAD_TOKENS = 4  # Tokens for message formatting

# Retry Configuration
MAX_RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT = 1.0  # seconds
RETRY_MAX_WAIT = 10.0  # seconds
RETRY_MULTIPLIER = 2.0  # Exponential backoff

# Rate Limiting
DEFAULT_RATE_LIMIT_CALLS = 100  # Calls per period
DEFAULT_RATE_LIMIT_PERIOD = 60  # Period in seconds

# Security
BLOCKED_COMMAND_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"mkfs\.",
    r"dd\s+if=/dev/zero",
    r">\s*/dev/sd",
    r":\(\)\s*{\s*:\|:\s*&\s*}\s*;",  # Fork bomb
    r"chmod\s+-R\s+777",
    r"chown\s+-R\s+root",
]

# Ignore patterns for directory listing
IGNORE_PATTERNS = {
    "node_modules",
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    ".idea",
    ".vscode",
    ".vs",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "Thumbs.db",
}

# Native tool calling models
NATIVE_TOOL_MODELS = {
    "qwen2.5",
    "qwen2",
    "qwen3",
    "llama3.1",
    "llama3.2",
    "mistral",
}

# Provider URLs
OLLAMA_DEFAULT_URL = "http://localhost:11434"
OPENAI_COMPATIBLE_DEFAULT_URL = "http://localhost:1234/v1"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# Logging
LOG_FORMAT = "%(timestamp)s [%(level)s] %(event)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "agent.log"
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Metrics
METRICS_PORT = 8000
METRICS_ENABLED = True

# Health Check
HEALTH_CHECK_INTERVAL = 60  # seconds
