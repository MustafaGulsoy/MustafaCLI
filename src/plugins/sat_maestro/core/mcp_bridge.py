"""MCP Bridge - central communication layer for all MCP server calls."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    """Configuration for an MCP server connection."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


class McpBridge:
    """Central bridge for calling tools on MCP servers.

    All SAT-MAESTRO agents use this bridge to communicate with
    external tools (Neo4j, FreeCAD, CalculiX, Gmsh) via MCP protocol.
    Falls back to direct Neo4j client when MCP server is not available.
    """

    def __init__(self, servers: dict[str, McpServerConfig] | None = None,
                 neo4j_client: Any = None) -> None:
        self._server_configs = servers or {}
        self._clients: dict[str, Any] = {}
        self._sessions: dict[str, Any] = {}
        self._neo4j_direct = neo4j_client  # Direct fallback for Neo4j

    @property
    def servers(self) -> dict[str, McpServerConfig]:
        return self._server_configs

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected."""
        return server_name in self._sessions

    async def connect(self, server_name: str) -> None:
        """Connect to an MCP server by name."""
        if server_name not in self._server_configs:
            raise ValueError(f"Unknown MCP server: {server_name}")

        config = self._server_configs[server_name]

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env or None,
            )

            client = stdio_client(params)
            read, write = await client.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()

            self._clients[server_name] = client
            self._sessions[server_name] = session
            logger.info("Connected to MCP server: %s", server_name)

        except Exception as e:
            logger.error("Failed to connect to MCP server %s: %s", server_name, e)
            raise

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server."""
        if server_name in self._sessions:
            try:
                await self._sessions[server_name].__aexit__(None, None, None)
                await self._clients[server_name].__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error disconnecting from %s: %s", server_name, e)
            finally:
                del self._sessions[server_name]
                del self._clients[server_name]

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._sessions.keys()):
            await self.disconnect(name)

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on an MCP server and return the result."""
        if server_name not in self._sessions:
            raise RuntimeError(f"MCP server '{server_name}' not connected. Call connect() first.")

        session = self._sessions[server_name]
        result = await session.call_tool(tool_name, arguments or {})

        if result.isError:
            error_text = result.content[0].text if result.content else "Unknown error"
            raise RuntimeError(f"MCP tool '{tool_name}' error: {error_text}")

        # Extract text content from result
        if result.content and hasattr(result.content[0], 'text'):
            import json
            text = result.content[0].text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text

        return result.content

    # -- Convenience methods for common operations --

    async def neo4j_query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a Cypher query. Uses direct client if MCP not connected."""
        if self._neo4j_direct and not self.is_connected("neo4j"):
            return await self._neo4j_direct.execute(cypher, params)
        return await self.call_tool("neo4j", "read_neo4j_cypher", {
            "query": cypher,
            "params": params or {},
        })

    async def neo4j_write(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Execute a write query. Uses direct client if MCP not connected."""
        if self._neo4j_direct and not self.is_connected("neo4j"):
            return await self._neo4j_direct.execute_write(cypher, params)
        return await self.call_tool("neo4j", "write_neo4j_cypher", {
            "query": cypher,
            "params": params or {},
        })

    async def neo4j_schema(self) -> dict:
        """Get Neo4j database schema."""
        if self._neo4j_direct and not self.is_connected("neo4j"):
            return await self._neo4j_direct.execute(
                "CALL db.schema.visualization()"
            )
        return await self.call_tool("neo4j", "get_neo4j_schema", {})

    async def freecad_execute(self, code: str) -> Any:
        """Execute Python code in FreeCAD context."""
        return await self.call_tool("freecad", "execute_code", {"code": code})

    async def freecad_import_step(self, file_path: str) -> dict:
        """Import a STEP file via FreeCAD MCP."""
        return await self.freecad_execute(
            f"import Part; Part.open('{file_path}'); "
            f"doc = FreeCAD.ActiveDocument; "
            f"[{{'name': o.Label, 'type': o.TypeId}} for o in doc.Objects]"
        )

    async def freecad_mass_properties(self, body_name: str = "") -> dict:
        """Get mass properties (mass, CoG, inertia) from FreeCAD."""
        code = """
import FreeCAD
doc = FreeCAD.ActiveDocument
shapes = [o.Shape for o in doc.Objects if hasattr(o, 'Shape')]
if shapes:
    compound = Part.makeCompound(shapes)
    props = compound.ShapeInfo if hasattr(compound, 'ShapeInfo') else {}
    result = {
        'mass': compound.Mass,
        'volume': compound.Volume,
        'cog': list(compound.CenterOfGravity),
        'inertia': list(compound.MatrixOfInertia),
    }
else:
    result = {'error': 'No shapes found'}
result
"""
        return await self.freecad_execute(code)

    async def gmsh_mesh(self, step_file: str, element_size: float = 5.0,
                         element_type: str = "tet", order: int = 2) -> str:
        """Generate FEM mesh from STEP file via Gmsh MCP."""
        return await self.call_tool("gmsh", "gmsh_mesh_from_step", {
            "step_file": step_file,
            "element_size": element_size,
            "element_type": element_type,
            "order": order,
        })

    async def gmsh_quality(self, mesh_file: str) -> dict:
        """Check mesh quality via Gmsh MCP."""
        return await self.call_tool("gmsh", "gmsh_quality_check", {
            "mesh_file": mesh_file,
        })

    async def calculix_solve(self, input_file: str, solve_type: str = "static") -> dict:
        """Run CalculiX solver via MCP."""
        tool_map = {
            "static": "ccx_solve_static",
            "modal": "ccx_solve_modal",
            "thermal": "ccx_solve_thermal",
            "buckling": "ccx_solve_buckling",
        }
        tool = tool_map.get(solve_type, "ccx_solve_static")
        return await self.call_tool("calculix", tool, {"input_file": input_file})

    async def calculix_results(self, result_file: str, field: str = "stress") -> dict:
        """Read CalculiX results via MCP."""
        return await self.call_tool("calculix", "ccx_read_results", {
            "result_file": result_file,
            "field": field,
        })
