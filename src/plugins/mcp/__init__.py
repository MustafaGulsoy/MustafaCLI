"""MCP (Model Context Protocol) support - server and client."""
from .protocol import MCPMessage, MCPMethod, make_response, make_error
from .server import MCPServer
from .client import MCPClient
