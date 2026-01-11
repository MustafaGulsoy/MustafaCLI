"""
Configuration Management - Pydantic-based Settings
===================================================

Type-safe configuration management with environment variable support.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import (
    DEFAULT_BASH_TIMEOUT,
    DEFAULT_COMPACTION_THRESHOLD,
    DEFAULT_CONTEXT_RESERVE_TOKENS,
    DEFAULT_KEEP_RECENT_MESSAGES,
    DEFAULT_MAX_CONSECUTIVE_TOOL_CALLS,
    DEFAULT_MAX_CONTEXT_TOKENS,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_THINKING_BUDGET,
    DEFAULT_TOOL_TIMEOUT,
)


class AgentSettings(BaseSettings):
    """
    Agent configuration with environment variable support.

    Environment variables should be prefixed with AGENT_
    Example: AGENT_MODEL_NAME=qwen2.5-coder:32b
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Model settings
    model_name: str = Field(
        default=DEFAULT_MODEL,
        description="LLM model name",
    )
    temperature: float = Field(
        default=DEFAULT_TEMPERATURE,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0 = deterministic)",
    )
    max_tokens: int = Field(
        default=DEFAULT_MAX_TOKENS,
        gt=0,
        le=128000,
        description="Maximum tokens per response",
    )

    # Agent loop settings
    max_iterations: int = Field(
        default=DEFAULT_MAX_ITERATIONS,
        gt=0,
        le=1000,
        description="Maximum agent iterations",
    )
    max_consecutive_tool_calls: int = Field(
        default=DEFAULT_MAX_CONSECUTIVE_TOOL_CALLS,
        gt=0,
        le=100,
        description="Maximum consecutive tool calls before breaking",
    )
    thinking_budget: int = Field(
        default=DEFAULT_THINKING_BUDGET,
        gt=0,
        description="Token budget for extended thinking",
    )

    # Context management
    max_context_tokens: int = Field(
        default=DEFAULT_MAX_CONTEXT_TOKENS,
        gt=0,
        le=200000,
        description="Maximum context window size",
    )
    context_reserve_tokens: int = Field(
        default=DEFAULT_CONTEXT_RESERVE_TOKENS,
        gt=0,
        description="Tokens reserved for response generation",
    )
    compaction_threshold: float = Field(
        default=DEFAULT_COMPACTION_THRESHOLD,
        ge=0.5,
        le=0.95,
        description="Context usage ratio that triggers compaction",
    )
    keep_recent_messages: int = Field(
        default=DEFAULT_KEEP_RECENT_MESSAGES,
        gt=0,
        description="Number of recent messages to keep after compaction",
    )

    # Tool settings
    tool_timeout: int = Field(
        default=DEFAULT_TOOL_TIMEOUT,
        gt=0,
        le=3600,
        description="Tool execution timeout in seconds",
    )
    bash_timeout: int = Field(
        default=DEFAULT_BASH_TIMEOUT,
        gt=0,
        le=3600,
        description="Bash command timeout in seconds",
    )

    # Working directory
    working_dir: Path = Field(
        default=Path("."),
        description="Working directory for agent operations",
    )

    # Skills directory
    skills_dir: Optional[Path] = Field(
        default=None,
        description="Directory containing skill definitions",
    )

    # Safety settings
    allow_dangerous_commands: bool = Field(
        default=False,
        description="Allow potentially dangerous commands",
    )
    blocked_commands: List[str] = Field(
        default_factory=list,
        description="Additional command patterns to block",
    )

    # Performance settings
    enable_parallel_tools: bool = Field(
        default=True,
        description="Enable parallel tool execution when possible",
    )
    enable_caching: bool = Field(
        default=True,
        description="Enable response caching",
    )

    # Observability
    enable_metrics: bool = Field(
        default=True,
        description="Enable Prometheus metrics",
    )
    metrics_port: int = Field(
        default=8000,
        gt=1024,
        lt=65535,
        description="Port for metrics server",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    log_file: Optional[Path] = Field(
        default=None,
        description="Log file path (None = console only)",
    )
    json_logs: bool = Field(
        default=False,
        description="Use JSON format for logs",
    )

    @field_validator("working_dir", mode="before")
    @classmethod
    def resolve_working_dir(cls, v: str | Path) -> Path:
        """Resolve working directory to absolute path."""
        path = Path(v)
        return path.resolve()

    @field_validator("skills_dir", mode="before")
    @classmethod
    def resolve_skills_dir(cls, v: Optional[str | Path]) -> Optional[Path]:
        """Resolve skills directory to absolute path."""
        if v is None:
            return None
        path = Path(v)
        return path.resolve()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper


class ProviderSettings(BaseSettings):
    """Provider-specific configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PROVIDER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Provider type
    provider_type: str = Field(
        default="ollama",
        description="Provider type (ollama, openai, anthropic)",
    )

    # Provider URLs
    ollama_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL",
    )
    openai_url: str = Field(
        default="http://localhost:1234/v1",
        description="OpenAI-compatible API base URL",
    )

    # Timeouts
    http_timeout: int = Field(
        default=300,
        gt=0,
        le=3600,
        description="HTTP request timeout in seconds",
    )

    # Retry settings
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts",
    )
    retry_min_wait: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Minimum wait time between retries (seconds)",
    )
    retry_max_wait: float = Field(
        default=10.0,
        ge=1.0,
        le=300.0,
        description="Maximum wait time between retries (seconds)",
    )


def load_settings() -> tuple[AgentSettings, ProviderSettings]:
    """
    Load all settings from environment and .env file.

    Returns:
        tuple[AgentSettings, ProviderSettings]: Agent and provider settings
    """
    agent_settings = AgentSettings()
    provider_settings = ProviderSettings()
    return agent_settings, provider_settings
