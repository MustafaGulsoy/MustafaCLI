"""
Observability - Prometheus Metrics
===================================

Metrics collection and monitoring endpoints.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
from typing import Optional
import time

from .logging_config import get_logger

logger = get_logger(__name__)

# Agent metrics
agent_iterations_total = Counter(
    "agent_iterations_total",
    "Total number of agent iterations",
    ["model", "status"],
)

agent_tool_calls_total = Counter(
    "agent_tool_calls_total",
    "Total number of tool calls",
    ["tool_name", "status"],
)

agent_iteration_duration = Histogram(
    "agent_iteration_duration_seconds",
    "Agent iteration duration",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# Context metrics
context_tokens_used = Gauge(
    "context_tokens_used",
    "Current context tokens used",
)

context_messages_count = Gauge(
    "context_messages_count",
    "Current number of messages in context",
)

context_compactions_total = Counter(
    "context_compactions_total",
    "Total number of context compactions",
)

# Tool metrics
tool_execution_duration = Histogram(
    "tool_execution_duration_seconds",
    "Tool execution duration",
    ["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

tool_errors_total = Counter(
    "tool_errors_total",
    "Total number of tool execution errors",
    ["tool_name", "error_type"],
)

# Model provider metrics
provider_requests_total = Counter(
    "provider_requests_total",
    "Total number of provider API requests",
    ["provider", "model", "status"],
)

provider_request_duration = Histogram(
    "provider_request_duration_seconds",
    "Provider API request duration",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

provider_tokens_used = Counter(
    "provider_tokens_used_total",
    "Total tokens used from provider",
    ["provider", "model", "type"],  # type: prompt, completion
)

# Application info
app_info = Info("app", "Application information")
app_info.info({
    "version": "0.1.0",
    "name": "local-agent-cli",
})


class MetricsServer:
    """Prometheus metrics server."""

    def __init__(self, port: int = 8000, enabled: bool = True):
        self.port = port
        self.enabled = enabled
        self._started = False

    def start(self) -> None:
        """Start metrics server."""
        if not self.enabled:
            logger.info("metrics_disabled")
            return

        if self._started:
            logger.warning("metrics_already_started")
            return

        try:
            start_http_server(self.port)
            self._started = True
            logger.info("metrics_started", port=self.port)
        except Exception as e:
            logger.error("metrics_start_failed", error=str(e))


# Convenience functions
def record_agent_iteration(model: str, status: str, duration: float) -> None:
    """Record agent iteration metrics."""
    agent_iterations_total.labels(model=model, status=status).inc()
    agent_iteration_duration.labels(model=model).observe(duration)


def record_tool_call(tool_name: str, status: str, duration: float) -> None:
    """Record tool call metrics."""
    agent_tool_calls_total.labels(tool_name=tool_name, status=status).inc()
    tool_execution_duration.labels(tool_name=tool_name).observe(duration)


def record_tool_error(tool_name: str, error_type: str) -> None:
    """Record tool error."""
    tool_errors_total.labels(tool_name=tool_name, error_type=error_type).inc()


def record_provider_request(
    provider: str,
    model: str,
    status: str,
    duration: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    """Record provider request metrics."""
    provider_requests_total.labels(provider=provider, model=model, status=status).inc()
    provider_request_duration.labels(provider=provider, model=model).observe(duration)

    if prompt_tokens > 0:
        provider_tokens_used.labels(provider=provider, model=model, type="prompt").inc(
            prompt_tokens
        )
    if completion_tokens > 0:
        provider_tokens_used.labels(
            provider=provider, model=model, type="completion"
        ).inc(completion_tokens)


def update_context_metrics(tokens: int, messages: int) -> None:
    """Update context metrics."""
    context_tokens_used.set(tokens)
    context_messages_count.set(messages)


def record_context_compaction() -> None:
    """Record context compaction."""
    context_compactions_total.inc()
