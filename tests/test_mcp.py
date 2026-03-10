"""Tests for MCP protocol support."""
from __future__ import annotations

import pytest

from src.plugins.mcp.protocol import MCPMessage, MCPMethod, make_response, make_error


class TestMCPProtocol:
    def test_message_serialize(self):
        msg = MCPMessage(method=MCPMethod.TOOLS_LIST, id="1")
        data = msg.to_dict()
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "tools/list"
        assert data["id"] == "1"

    def test_message_deserialize(self):
        data = {"jsonrpc": "2.0", "method": "tools/list", "id": "1", "params": {}}
        msg = MCPMessage.from_dict(data)
        assert msg.method == MCPMethod.TOOLS_LIST
        assert msg.id == "1"

    def test_message_with_params(self):
        msg = MCPMessage(
            method=MCPMethod.TOOLS_CALL,
            id="2",
            params={"name": "bash", "arguments": {"command": "ls"}},
        )
        data = msg.to_dict()
        assert data["params"]["name"] == "bash"
        assert data["params"]["arguments"]["command"] == "ls"

    def test_unknown_method_defaults_to_initialize(self):
        data = {"jsonrpc": "2.0", "method": "unknown/method", "id": "1"}
        msg = MCPMessage.from_dict(data)
        assert msg.method == MCPMethod.INITIALIZE

    def test_make_response(self):
        resp = make_response("1", {"tools": []})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "1"
        assert resp["result"]["tools"] == []

    def test_make_error(self):
        resp = make_error("1", -32601, "Method not found")
        assert resp["error"]["code"] == -32601
        assert resp["error"]["message"] == "Method not found"

    def test_all_methods(self):
        methods = list(MCPMethod)
        assert len(methods) == 7
        assert MCPMethod.TOOLS_LIST in methods
        assert MCPMethod.TOOLS_CALL in methods


class TestMCPServer:
    @pytest.mark.asyncio
    async def test_initialize(self):
        from src.plugins.mcp.server import MCPServer
        from unittest.mock import MagicMock

        registry = MagicMock()
        server = MCPServer(registry)

        result = await server.handle_request({
            "jsonrpc": "2.0", "method": "initialize", "id": "1", "params": {}
        })
        assert "result" in result
        assert result["result"]["protocolVersion"] == "2024-11-05"
        assert result["result"]["serverInfo"]["name"] == "mustafacli"

    @pytest.mark.asyncio
    async def test_tools_list(self):
        from src.plugins.mcp.server import MCPServer
        from unittest.mock import MagicMock

        registry = MagicMock()
        registry.get_tool_definitions.return_value = [
            {"function": {"name": "bash", "description": "Run commands", "parameters": {}}}
        ]
        server = MCPServer(registry)

        result = await server.handle_request({
            "jsonrpc": "2.0", "method": "tools/list", "id": "1", "params": {}
        })
        assert "result" in result
        tools = result["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "bash"

    @pytest.mark.asyncio
    async def test_unknown_method(self):
        from src.plugins.mcp.server import MCPServer
        from unittest.mock import MagicMock

        registry = MagicMock()
        server = MCPServer(registry)

        result = await server.handle_request({
            "jsonrpc": "2.0", "method": "resources/list", "id": "1", "params": {}
        })
        assert "error" in result
        assert result["error"]["code"] == -32601
