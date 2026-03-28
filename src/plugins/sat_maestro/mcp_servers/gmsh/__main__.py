"""Entry point: python -m src.plugins.sat_maestro.mcp_servers.gmsh"""
from .server import main
import asyncio

asyncio.run(main())
