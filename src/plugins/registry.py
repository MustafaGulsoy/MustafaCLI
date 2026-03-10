"""
Plugin Registry - Central plugin management
============================================

Manages plugin registration, lifecycle, tool aggregation,
and hook dispatching.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

from typing import Any, Type

from ..core.logging_config import get_logger
from .base import PluginBase, PluginTool
from .hooks import HookEvent

logger = get_logger(__name__)

# Map HookEvent values to PluginBase method names
_HOOK_METHOD_MAP: dict[HookEvent, str] = {
    HookEvent.AGENT_START: "on_agent_start",
    HookEvent.AGENT_END: "on_agent_end",
    HookEvent.TOOL_CALL: "on_tool_call",
    HookEvent.TOOL_RESULT: "on_tool_result",
    # SESSION_CREATE and SESSION_END have no default handler on PluginBase,
    # but plugins can still implement them — the dispatcher will just skip
    # plugins that don't have a matching method.
    HookEvent.SESSION_CREATE: "on_session_create",
    HookEvent.SESSION_END: "on_session_end",
}


class PluginRegistry:
    """Central registry that owns plugin instances and dispatches hooks."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}

    # -- Registration ------------------------------------------------------

    def register(self, plugin_cls: Type[PluginBase] | PluginBase) -> None:
        """
        Register a plugin class (will be instantiated) or an existing instance.
        """
        if isinstance(plugin_cls, type) and issubclass(plugin_cls, PluginBase):
            instance = plugin_cls()
        elif isinstance(plugin_cls, PluginBase):
            instance = plugin_cls
        else:
            raise TypeError(f"Expected PluginBase subclass or instance, got {type(plugin_cls)}")

        name = instance.metadata.name
        if name in self._plugins:
            logger.warning("plugin_already_registered", plugin=name)
            return
        self._plugins[name] = instance
        logger.info("plugin_registered", plugin=name, version=instance.metadata.version)

    def unregister(self, name: str) -> None:
        """Remove a plugin by name."""
        if name in self._plugins:
            del self._plugins[name]
            logger.info("plugin_unregistered", plugin=name)

    # -- Queries -----------------------------------------------------------

    def list_plugins(self) -> list[PluginBase]:
        """Return all registered plugin instances."""
        return list(self._plugins.values())

    def get_plugin(self, name: str) -> PluginBase | None:
        """Get a plugin by name, or ``None`` if not found."""
        return self._plugins.get(name)

    def get_all_tools(self) -> list[PluginTool]:
        """Aggregate tools from every registered plugin."""
        tools: list[PluginTool] = []
        for plugin in self._plugins.values():
            tools.extend(plugin.get_tools())
        return tools

    # -- Lifecycle ---------------------------------------------------------

    async def initialize_all(self) -> None:
        """Initialize every registered plugin."""
        for name, plugin in self._plugins.items():
            try:
                await plugin.initialize()
                logger.info("plugin_initialized", plugin=name)
            except Exception as exc:
                logger.error("plugin_init_error", plugin=name, error=str(exc))

    async def shutdown_all(self) -> None:
        """Shutdown every registered plugin."""
        for name, plugin in self._plugins.items():
            try:
                await plugin.shutdown()
                logger.info("plugin_shutdown", plugin=name)
            except Exception as exc:
                logger.error("plugin_shutdown_error", plugin=name, error=str(exc))

    # -- Hook dispatching --------------------------------------------------

    async def fire_hook(self, hook_name: str | HookEvent, **kwargs: Any) -> None:
        """
        Fire a lifecycle hook on all registered plugins.

        ``hook_name`` can be a ``HookEvent`` enum member or a plain string
        matching a method name on ``PluginBase``.
        """
        if isinstance(hook_name, HookEvent):
            method_name = _HOOK_METHOD_MAP.get(hook_name, hook_name.name.lower())
        else:
            method_name = hook_name

        for name, plugin in self._plugins.items():
            handler = getattr(plugin, method_name, None)
            if handler is None or not callable(handler):
                continue
            try:
                await handler(**kwargs)
            except Exception as exc:
                logger.error(
                    "plugin_hook_error",
                    plugin=name,
                    hook=method_name,
                    error=str(exc),
                )
