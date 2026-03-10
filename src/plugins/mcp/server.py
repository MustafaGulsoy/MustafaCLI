"""MCP Server - expose MustafaCLI tools as MCP endpoints."""
from __future__ import annotations

from typing import Any

from .protocol import MCPMessage, MCPMethod, make_error, make_response
from ...core.tools import ToolRegistry


class MCPServer:
    """Expose local tools via MCP JSON-RPC protocol."""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry
        self._handlers = {
            MCPMethod.INITIALIZE: self._handle_initialize,
            MCPMethod.TOOLS_LIST: self._handle_tools_list,
            MCPMethod.TOOLS_CALL: self._handle_tools_call,
        }

    async def handle_request(self, data: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming MCP request."""
        msg = MCPMessage.from_dict(data)
        handler = self._handlers.get(msg.method)
        if not handler:
            return make_error(msg.id, -32601, f"Method not found: {msg.method.value}")
        return await handler(msg)

    async def _handle_initialize(self, msg: MCPMessage) -> dict[str, Any]:
        return make_response(msg.id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "mustafacli", "version": "0.5.0"},
            "capabilities": {"tools": {"listChanged": False}},
        })

    async def _handle_tools_list(self, msg: MCPMessage) -> dict[str, Any]:
        tools = []
        for defn in self.tool_registry.get_tool_definitions():
            func = defn.get("function", {})
            tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "inputSchema": func.get("parameters", {}),
            })
        return make_response(msg.id, {"tools": tools})

    async def _handle_tools_call(self, msg: MCPMessage) -> dict[str, Any]:
        tool_name = msg.params.get("name", "")
        arguments = msg.params.get("arguments", {})

        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return make_error(msg.id, -32602, f"Tool not found: {tool_name}")

        result = await tool.execute(**arguments)
        return make_response(msg.id, {
            "content": [{"type": "text", "text": result.output}],
            "isError": not result.success,
        })
