"""MCP (Model Context Protocol) message types and helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MCPMethod(str, Enum):
    """MCP JSON-RPC method names."""
    INITIALIZE = "initialize"
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"


_METHOD_VALUES = {m.value for m in MCPMethod}


@dataclass
class MCPMessage:
    """MCP JSON-RPC 2.0 message."""
    method: MCPMethod
    id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method.value, "id": self.id}
        if self.params:
            d["params"] = self.params
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPMessage:
        method_str = data.get("method", "")
        if method_str in _METHOD_VALUES:
            method = MCPMethod(method_str)
        else:
            method = MCPMethod.INITIALIZE
        return cls(
            method=method,
            id=data.get("id", ""),
            params=data.get("params", {}),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )


def make_response(id: str, result: Any) -> dict[str, Any]:
    """Create a JSON-RPC success response."""
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error(id: str, code: int, message: str) -> dict[str, Any]:
    """Create a JSON-RPC error response."""
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
