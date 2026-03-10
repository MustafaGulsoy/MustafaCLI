"""
Plugin Base - Core abstractions for the plugin system
======================================================

Provides the PluginBase ABC, PluginMetadata dataclass,
@plugin_tool decorator, and PluginTool wrapper.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

import asyncio
import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Optional, get_type_hints

from ..core.logging_config import get_logger
from ..core.tools import Tool, ToolResult

logger = get_logger(__name__)

# Type-hint to JSON Schema type mapping
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class PluginMetadata:
    """Metadata describing a plugin."""

    name: str
    version: str
    description: str
    author: str = ""
    requires: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    license: str = ""


def _extract_params(func: Callable) -> dict:
    """
    Auto-generate a JSON Schema parameters dict from a function's type hints.

    Skips ``self`` and ``return`` annotations. Parameters without a default
    value are marked as required.
    """
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    properties: dict[str, dict[str, str]] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        param_type = hints.get(param_name, str)
        # Resolve Optional / Union types to their first concrete type
        origin = getattr(param_type, "__origin__", None)
        if origin is not None:
            args = getattr(param_type, "__args__", ())
            if args:
                param_type = args[0]

        json_type = _TYPE_MAP.get(param_type, "string")
        properties[param_name] = {"type": json_type}

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def plugin_tool(
    name: str | None = None,
    description: str | None = None,
    parameters: dict | None = None,
) -> Callable:
    """
    Decorator that marks a method as a plugin tool.

    Can be used with or without arguments::

        @plugin_tool
        async def greet(self, name: str) -> ToolResult: ...

        @plugin_tool(name="greet", description="Say hello")
        async def greet(self, name: str) -> ToolResult: ...
    """

    def decorator(func: Callable) -> Callable:
        func._plugin_tool = True  # noqa: SLF001
        func._tool_name = name or func.__name__  # noqa: SLF001
        func._tool_description = description or (func.__doc__ or "").strip()  # noqa: SLF001
        func._tool_parameters = parameters  # noqa: SLF001
        return func

    # Allow bare @plugin_tool usage (without parentheses)
    if callable(name):
        func = name
        name = None
        return decorator(func)

    return decorator


class PluginTool(Tool):
    """
    Wraps a decorated plugin method so it satisfies the agent's Tool ABC.

    Handles both synchronous and asynchronous tool functions transparently.
    """

    def __init__(self, func: Callable, plugin_instance: PluginBase) -> None:
        self._func = func
        self._plugin = plugin_instance
        self._name: str = getattr(func, "_tool_name", func.__name__)
        self._description: str = getattr(func, "_tool_description", "") or ""
        explicit_params: dict | None = getattr(func, "_tool_parameters", None)
        self._parameters: dict = explicit_params if explicit_params is not None else _extract_params(func)

    # -- Tool ABC implementation ------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the wrapped tool function, handling sync/async transparently."""
        try:
            result = self._func(self._plugin, **kwargs)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                result = await result
            return result
        except Exception as exc:
            logger.error("plugin_tool_error", tool=self._name, error=str(exc))
            return ToolResult(success=False, output="", error=str(exc))


class PluginBase(ABC):
    """
    Abstract base class that all plugins must subclass.

    Subclasses must provide ``metadata`` and may override lifecycle hooks.
    Methods decorated with ``@plugin_tool`` are automatically discovered by
    ``get_tools()``.
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return metadata describing this plugin."""
        ...

    # -- Lifecycle ---------------------------------------------------------

    async def initialize(self) -> None:
        """Called once when the plugin is loaded. Override for setup work."""

    async def shutdown(self) -> None:
        """Called once when the plugin is unloaded. Override for cleanup."""

    # -- Hooks -------------------------------------------------------------

    async def on_agent_start(self, **kwargs: Any) -> None:
        """Fired when the agent starts a new run."""

    async def on_agent_end(self, **kwargs: Any) -> None:
        """Fired when the agent completes a run."""

    async def on_tool_call(self, **kwargs: Any) -> None:
        """Fired just before a tool is executed."""

    async def on_tool_result(self, **kwargs: Any) -> None:
        """Fired right after a tool returns a result."""

    # -- Tool discovery ----------------------------------------------------

    def get_tools(self) -> list[PluginTool]:
        """Return PluginTool wrappers for every @plugin_tool method."""
        tools: list[PluginTool] = []
        for attr_name in dir(self):
            try:
                attr = getattr(self, attr_name)
            except Exception:
                continue
            if callable(attr) and getattr(attr, "_plugin_tool", False):
                # attr is a bound method; get the underlying function
                func = getattr(attr, "__func__", attr)
                tools.append(PluginTool(func, self))
        return tools
