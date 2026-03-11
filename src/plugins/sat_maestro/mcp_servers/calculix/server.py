"""CalculiX MCP Server - FEM solver via Model Context Protocol."""
from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .solver import CalculixSolver

logger = logging.getLogger(__name__)

app = Server("mcp-calculix")
solver = CalculixSolver()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="ccx_solve_static", description="Run static structural analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "num_cpus": {"type": "integer", "default": 1},
             }, "required": ["input_file"]}),
        Tool(name="ccx_solve_modal", description="Run modal (frequency) analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "num_modes": {"type": "integer", "default": 20},
             }, "required": ["input_file"]}),
        Tool(name="ccx_solve_thermal", description="Run thermal analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"},
             }, "required": ["input_file"]}),
        Tool(name="ccx_solve_buckling", description="Run buckling analysis",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"}, "num_modes": {"type": "integer", "default": 5},
             }, "required": ["input_file"]}),
        Tool(name="ccx_read_results", description="Read FEM result file",
             inputSchema={"type": "object", "properties": {
                 "result_file": {"type": "string"}, "field": {"type": "string", "default": "stress"},
             }, "required": ["result_file"]}),
        Tool(name="ccx_check_input", description="Validate CalculiX input file",
             inputSchema={"type": "object", "properties": {
                 "input_file": {"type": "string"},
             }, "required": ["input_file"]}),
        Tool(name="ccx_get_version", description="Get CalculiX version",
             inputSchema={"type": "object", "properties": {}}),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name in ("ccx_solve_static", "ccx_solve_modal", "ccx_solve_thermal", "ccx_solve_buckling"):
            result = await solver.solve(arguments["input_file"], arguments.get("num_cpus", 1))
        elif name == "ccx_read_results":
            from pathlib import Path
            from .result_parser import CalculixResultParser
            parser = CalculixResultParser()
            content = Path(arguments["result_file"]).read_text(encoding="utf-8", errors="replace")
            field = arguments.get("field", "stress")
            if field == "stress":
                result = parser.parse_dat_stress(content)
            elif field == "displacement":
                result = parser.parse_dat_displacement(content)
            elif field == "frequency":
                result = parser.parse_dat_frequencies(content)
            else:
                result = {"error": f"Unknown field: {field}"}
        elif name == "ccx_check_input":
            result = await solver.check_input(arguments["input_file"])
        elif name == "ccx_get_version":
            result = {"version": solver.get_version()}
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
