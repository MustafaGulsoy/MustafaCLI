"""
Exception Hierarchy - Custom Exceptions
========================================

Structured exception hierarchy for better error handling and debugging.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from typing import Any, Optional


class AgentError(Exception):
    """Base exception for all agent-related errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(AgentError):
    """Configuration-related errors."""

    pass


class ModelError(AgentError):
    """Base class for model-related errors."""

    pass


class ModelAPIError(ModelError):
    """Model API call failed."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body


class ModelTimeoutError(ModelError):
    """Model API call timed out."""

    pass


class ModelRateLimitError(ModelError):
    """Model API rate limit exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.retry_after = retry_after


class ToolError(AgentError):
    """Base class for tool-related errors."""

    pass


class ToolExecutionError(ToolError):
    """Tool execution failed."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        exit_code: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.tool_name = tool_name
        self.exit_code = exit_code


class ToolTimeoutError(ToolError):
    """Tool execution timed out."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        timeout: int,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.tool_name = tool_name
        self.timeout = timeout


class ToolNotFoundError(ToolError):
    """Requested tool not found in registry."""

    def __init__(self, tool_name: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(f"Tool not found: {tool_name}", details)
        self.tool_name = tool_name


class SecurityError(AgentError):
    """Security-related errors."""

    pass


class CommandBlockedError(SecurityError):
    """Command blocked by security policy."""

    def __init__(
        self,
        message: str,
        command: str,
        pattern: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.command = command
        self.pattern = pattern


class PathTraversalError(SecurityError):
    """Path traversal attempt detected."""

    def __init__(
        self, message: str, path: str, details: Optional[dict[str, Any]] = None
    ) -> None:
        super().__init__(message, details)
        self.path = path


class ContextError(AgentError):
    """Context management errors."""

    pass


class ContextLimitExceededError(ContextError):
    """Context window limit exceeded."""

    def __init__(
        self,
        message: str,
        current_tokens: int,
        max_tokens: int,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens


class CompactionError(ContextError):
    """Context compaction failed."""

    pass


class ProviderError(AgentError):
    """Provider-related errors."""

    pass


class ProviderConnectionError(ProviderError):
    """Failed to connect to provider."""

    def __init__(
        self, message: str, provider: str, details: Optional[dict[str, Any]] = None
    ) -> None:
        super().__init__(message, details)
        self.provider = provider


class ProviderNotSupportedError(ProviderError):
    """Provider not supported."""

    def __init__(self, provider: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(f"Provider not supported: {provider}", details)
        self.provider = provider


class CircuitBreakerError(AgentError):
    """Circuit breaker opened - too many failures."""

    def __init__(
        self,
        message: str,
        failure_count: int,
        threshold: int,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.failure_count = failure_count
        self.threshold = threshold


class MaxIterationsExceededError(AgentError):
    """Maximum iterations exceeded."""

    def __init__(
        self,
        message: str,
        iterations: int,
        max_iterations: int,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.iterations = iterations
        self.max_iterations = max_iterations


class ValidationError(AgentError):
    """Input validation error."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.field = field
        self.value = value


class AuthenticationError(AgentError):
    """Authentication-related errors (login, token, permissions)."""

    pass


class PluginError(AgentError):
    """Plugin system errors (loading, initialization, execution)."""

    def __init__(
        self,
        message: str,
        plugin_name: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.plugin_name = plugin_name


class MCPError(AgentError):
    """MCP (Model Context Protocol) errors."""

    def __init__(
        self,
        message: str,
        method: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, details)
        self.method = method


class DatabaseError(AgentError):
    """Database connection and query errors."""

    pass
