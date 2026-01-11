"""
Local Agent CLI
===============

Claude Code architecture implementation for open source models.

Usage:
    from local_agent import Agent, AgentConfig, create_provider, create_default_tools
    
    # Create components
    config = AgentConfig(model_name="qwen2.5-coder:32b")
    provider = create_provider("ollama", model=config.model_name)
    tools = create_default_tools()
    
    # Create agent
    agent = Agent(config, provider, tools)
    
    # Run
    async for response in agent.run("Create a Python script"):
        print(response.content)
"""

from .core.agent import Agent, AgentConfig, AgentState, AgentResponse
from .core.tools import (
    Tool,
    ToolResult,
    ToolRegistry,
    BashTool,
    ViewTool,
    StrReplaceTool,
    CreateFileTool,
    create_default_tools,
)
from .core.context import (
    ContextManager,
    Message,
    MessageRole,
    TokenEstimator,
    SlidingWindowContext,
    PriorityContext,
)
from .core.providers import (
    ModelProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    AnthropicProvider,
    create_provider,
)

__version__ = "0.1.0"
__author__ = "Mustafa (Kardelen Yazılım)"

__all__ = [
    # Agent
    "Agent",
    "AgentConfig",
    "AgentState",
    "AgentResponse",
    # Tools
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "BashTool",
    "ViewTool",
    "StrReplaceTool",
    "CreateFileTool",
    "create_default_tools",
    # Context
    "ContextManager",
    "Message",
    "MessageRole",
    "TokenEstimator",
    "SlidingWindowContext",
    "PriorityContext",
    # Providers
    "ModelProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "create_provider",
]
