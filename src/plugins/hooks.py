"""
Plugin Hooks - Event system for plugin lifecycle
=================================================

Defines hook events that plugins can listen to and respond to
during the agent's lifecycle.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

from __future__ import annotations

from enum import Enum, auto


class HookEvent(Enum):
    """Events that plugins can hook into."""

    AGENT_START = auto()
    AGENT_END = auto()
    TOOL_CALL = auto()
    TOOL_RESULT = auto()
    SESSION_CREATE = auto()
    SESSION_END = auto()
