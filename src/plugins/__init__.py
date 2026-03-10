"""Full plugin system with entry_points, directory discovery, and MCP support."""

from .base import PluginBase, PluginMetadata, PluginTool, plugin_tool
from .registry import PluginRegistry
from .loader import load_all_plugins
