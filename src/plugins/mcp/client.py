"""MCP Client - consume external MCP tools via stdio transport."""
from __future__ import annotations

import asyncio
import json
from typing import Any


class MCPClient:
    """Connect to external MCP servers via stdio."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self.command = command
        self.env = env
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def connect(self) -> dict[str, Any]:
        """Start the MCP server process and initialize."""
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
        )
        return await self._send({
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "mustafacli", "version": "0.5.0"},
            },
        })

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        result = await self._send({"method": "tools/list", "params": {}})
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server."""
        result = await self._send({
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        contents = result.get("result", {}).get("content", [])
        return "\n".join(
            c.get("text", "") for c in contents if c.get("type") == "text"
        )

    async def disconnect(self) -> None:
        """Terminate the MCP server process."""
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None

    async def _send(self, data: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and read the response."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("Not connected to MCP server")

        self._request_id += 1
        data["jsonrpc"] = "2.0"
        data["id"] = str(self._request_id)

        msg = json.dumps(data) + "\n"
        self._process.stdin.write(msg.encode())
        await self._process.stdin.drain()

        line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30)
        if not line:
            raise RuntimeError("MCP server closed connection")
        return json.loads(line.decode())
