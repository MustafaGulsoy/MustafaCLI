"""Core components for Local Agent CLI"""

from .agent import Agent, AgentConfig, AgentState, AgentResponse
from .tools import (
    Tool,
    ToolResult,
    ToolRegistry,
    BashTool,
    ViewTool,
    StrReplaceTool,
    CreateFileTool,
    create_default_tools,
)
from .context import (
    ContextManager,
    Message,
    MessageRole,
    TokenEstimator,
)
from .providers import (
    ModelProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    AnthropicProvider,
    create_provider,
)
