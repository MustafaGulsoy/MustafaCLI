"""Gmsh MCP Server - mesh generation via Model Context Protocol."""
from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .mesher import GmshMesher

logger = logging.getLogger(__name__)

app = Server("mcp-gmsh")
mesher = GmshMesher()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="gmsh_mesh_from_step", description="Generate FEM mesh from STEP file",
             inputSchema={"type": "object", "properties": {
                 "step_file": {"type": "string"}, "element_size": {"type": "number", "default": 5.0},
                 "element_type": {"type": "string", "default": "tet"},
                 "order": {"type": "integer", "default": 2},
             }, "required": ["step_file"]}),
        Tool(name="gmsh_mesh_from_geo", description="Generate mesh from .geo script",
             inputSchema={"type": "object", "properties": {
                 "geo_file": {"type": "string"}, "element_size": {"type": "number", "default": 5.0},
             }, "required": ["geo_file"]}),
        Tool(name="gmsh_quality_check", description="Check mesh quality",
             inputSchema={"type": "object", "properties": {
                 "mesh_file": {"type": "string"}, "metric": {"type": "string", "default": "gamma"},
             }, "required": ["mesh_file"]}),
        Tool(name="gmsh_info", description="Get mesh statistics",
             inputSchema={"type": "object", "properties": {
                 "mesh_file": {"type": "string"},
             }, "required": ["mesh_file"]}),
        Tool(name="gmsh_convert", description="Convert mesh format",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "output_format": {"type": "string", "default": "inp"},
             }, "required": ["input_file"]}),
        Tool(name="gmsh_refine_region", description="Refine mesh in a box region",
             inputSchema={"type": "object", "properties": {
                 "mesh_file": {"type": "string"},
                 "region_box": {"type": "object"}, "target_size": {"type": "number"},
             }, "required": ["mesh_file", "region_box", "target_size"]}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "gmsh_mesh_from_step":
            result = mesher.mesh_from_step(**arguments)
        elif name == "gmsh_mesh_from_geo":
            result = mesher.mesh_from_geo(**arguments)
        elif name == "gmsh_quality_check":
            result = mesher.quality_check(**arguments)
        elif name == "gmsh_info":
            result = mesher.info(**arguments)
        elif name == "gmsh_convert":
            result = mesher.convert(arguments["input_file"], arguments.get("output_format", "inp"))
        elif name == "gmsh_refine_region":
            result = mesher.refine_region(arguments["mesh_file"],
                                          arguments["region_box"], arguments["target_size"])
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
