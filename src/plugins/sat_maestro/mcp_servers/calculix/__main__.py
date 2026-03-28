"""Entry point: python -m src.plugins.sat_maestro.mcp_servers.calculix"""
from .server import main
import asyncio

asyncio.run(main())
