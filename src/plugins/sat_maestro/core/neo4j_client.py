"""Async Neo4j client wrapper for SAT-MAESTRO."""
from __future__ import annotations

import logging
from typing import Any

from ..config import SatMaestroConfig

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Async wrapper around the Neo4j Python driver."""

    def __init__(self, config: SatMaestroConfig) -> None:
        self._config = config
        self._driver = None

    async def connect(self) -> None:
        """Establish connection to Neo4j."""
        try:
            from neo4j import AsyncGraphDatabase
        except ImportError:
            raise ImportError(
                "neo4j package required. Install with: pip install neo4j[async]"
            )

        self._driver = AsyncGraphDatabase.driver(
            self._config.neo4j_uri,
            auth=(self._config.neo4j_user, self._config.neo4j_password),
        )
        await self.verify_connection()
        logger.info("Connected to Neo4j at %s", self._config.neo4j_uri)

    async def verify_connection(self) -> bool:
        """Verify Neo4j connection is alive."""
        if not self._driver:
            return False
        try:
            async with self._driver.session(database=self._config.neo4j_database) as session:
                result = await session.run("RETURN 1 AS n")
                record = await result.single()
                return record is not None and record["n"] == 1
        except Exception as e:
            logger.error("Neo4j connection verification failed: %s", e)
            return False

    async def execute(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        if not self._driver:
            raise RuntimeError("Neo4j client not connected. Call connect() first.")

        async with self._driver.session(database=self._config.neo4j_database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict]:
        """Execute a write transaction."""
        if not self._driver:
            raise RuntimeError("Neo4j client not connected. Call connect() first.")

        async with self._driver.session(database=self._config.neo4j_database) as session:
            result = await session.execute_write(
                lambda tx: tx.run(query, parameters or {}).data()
            )
            return result

    async def close(self) -> None:
        """Close the Neo4j driver."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    @property
    def is_connected(self) -> bool:
        return self._driver is not None
