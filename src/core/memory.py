"""
Memory Management - Persistent Memory System
=============================================

Persistent memory for long-term context and knowledge storage.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

from .logging_config import get_logger

logger = get_logger(__name__)


class MemoryType(Enum):
    """Memory entry type."""
    FACT = "fact"
    PREFERENCE = "preference"
    PATTERN = "pattern"
    ERROR = "error"
    SUCCESS = "success"


@dataclass
class MemoryEntry:
    """Memory entry."""
    id: Optional[int] = None
    type: MemoryType = MemoryType.FACT
    key: str = ""
    value: str = ""
    context: str = ""
    confidence: float = 1.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    access_count: int = 0
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


class PersistentMemory:
    """
    SQLite-based persistent memory system.

    Stores facts, preferences, and patterns across sessions.

    Features:
    - Persistent storage (survives restarts)
    - Search and retrieval
    - Confidence scoring
    - Tag-based organization
    - Access tracking

    Example:
        memory = PersistentMemory("/path/to/memory.db")

        # Store fact
        memory.store(
            type=MemoryType.FACT,
            key="project_name",
            value="MustafaCLI",
            context="User mentioned project name",
        )

        # Retrieve
        entry = memory.retrieve("project_name")

        # Search
        results = memory.search(query="project", type=MemoryType.FACT)
    """

    def __init__(self, db_path: str = "agent_memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        logger.info("memory_initialized", db_path=str(self.db_path))

    def _init_database(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    context TEXT,
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    tags TEXT
                )
            """)

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON memory(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_key ON memory(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_confidence ON memory(confidence)")

            conn.commit()

    def store(
        self,
        type: MemoryType,
        key: str,
        value: str,
        context: str = "",
        confidence: float = 1.0,
        tags: List[str] = None,
    ) -> int:
        """
        Store memory entry.

        Args:
            type: Memory type
            key: Unique key
            value: Value to store
            context: Context information
            confidence: Confidence score (0-1)
            tags: Optional tags

        Returns:
            Entry ID
        """
        entry = MemoryEntry(
            type=type,
            key=key,
            value=value,
            context=context,
            confidence=confidence,
            tags=tags or [],
        )

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR REPLACE INTO memory
                (type, key, value, context, confidence, created_at, updated_at, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.type.value,
                    entry.key,
                    entry.value,
                    entry.context,
                    entry.confidence,
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat(),
                    json.dumps(entry.tags),
                ),
            )
            conn.commit()
            entry_id = cursor.lastrowid

        logger.info("memory_stored", key=key, type=type.value, id=entry_id)
        return entry_id

    def retrieve(self, key: str) -> Optional[MemoryEntry]:
        """
        Retrieve memory entry by key.

        Updates access count.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memory WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()

            if row:
                # Update access count
                conn.execute(
                    "UPDATE memory SET access_count = access_count + 1 WHERE key = ?",
                    (key,),
                )
                conn.commit()

                entry = self._row_to_entry(row)
                # Increment access_count in the returned entry to match database
                entry.access_count += 1
                logger.debug("memory_retrieved", key=key, access_count=entry.access_count)
                return entry

        return None

    def search(
        self,
        query: Optional[str] = None,
        type: Optional[MemoryType] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Search memory entries.

        Args:
            query: Search query (searches key, value, context)
            type: Filter by memory type
            min_confidence: Minimum confidence score
            limit: Maximum results

        Returns:
            List of matching entries
        """
        sql = "SELECT * FROM memory WHERE confidence >= ?"
        params = [min_confidence]

        if type:
            sql += " AND type = ?"
            params.append(type.value)

        if query:
            sql += " AND (key LIKE ? OR value LIKE ? OR context LIKE ?)"
            search_pattern = f"%{query}%"
            params.extend([search_pattern, search_pattern, search_pattern])

        sql += " ORDER BY confidence DESC, access_count DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        entries = [self._row_to_entry(row) for row in rows]
        logger.debug("memory_search", query=query, results=len(entries))
        return entries

    def update_confidence(self, key: str, confidence: float) -> bool:
        """Update confidence score for entry."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE memory SET confidence = ?, updated_at = ? WHERE key = ?",
                (confidence, datetime.now().isoformat(), key),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete(self, key: str) -> bool:
        """Delete memory entry."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM memory WHERE key = ?", (key,))
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info("memory_deleted", key=key)
        return deleted

    def get_by_type(self, type: MemoryType, limit: int = 100) -> List[MemoryEntry]:
        """Get all entries of specific type."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memory WHERE type = ? ORDER BY confidence DESC LIMIT ?",
                (type.value, limit),
            )
            rows = cursor.fetchall()

        return [self._row_to_entry(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN type = 'fact' THEN 1 ELSE 0 END) as facts,
                    SUM(CASE WHEN type = 'preference' THEN 1 ELSE 0 END) as preferences,
                    SUM(CASE WHEN type = 'pattern' THEN 1 ELSE 0 END) as patterns,
                    AVG(confidence) as avg_confidence,
                    SUM(access_count) as total_accesses
                FROM memory
            """)
            row = cursor.fetchone()

        return {
            "total_entries": row[0] or 0,
            "facts": row[1] or 0,
            "preferences": row[2] or 0,
            "patterns": row[3] or 0,
            "avg_confidence": round(row[4] or 0, 2),
            "total_accesses": row[5] or 0,
        }

    def clear(self, type: Optional[MemoryType] = None) -> int:
        """
        Clear memory entries.

        Args:
            type: If specified, only clear entries of this type

        Returns:
            Number of deleted entries
        """
        with sqlite3.connect(self.db_path) as conn:
            if type:
                cursor = conn.execute("DELETE FROM memory WHERE type = ?", (type.value,))
            else:
                cursor = conn.execute("DELETE FROM memory")
            conn.commit()
            count = cursor.rowcount

        logger.info("memory_cleared", type=type, count=count)
        return count

    def export_json(self, output_path: str) -> None:
        """Export memory to JSON file."""
        entries = self.search(limit=10000)  # Get all
        data = [asdict(entry) for entry in entries]

        # Convert datetime and enum to strings
        for entry in data:
            entry["type"] = entry["type"].value
            entry["created_at"] = entry["created_at"].isoformat()
            entry["updated_at"] = entry["updated_at"].isoformat()

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info("memory_exported", path=output_path, count=len(data))

    def import_json(self, input_path: str) -> int:
        """Import memory from JSON file."""
        with open(input_path, "r") as f:
            data = json.load(f)

        count = 0
        for entry_dict in data:
            self.store(
                type=MemoryType(entry_dict["type"]),
                key=entry_dict["key"],
                value=entry_dict["value"],
                context=entry_dict.get("context", ""),
                confidence=entry_dict.get("confidence", 1.0),
                tags=entry_dict.get("tags", []),
            )
            count += 1

        logger.info("memory_imported", path=input_path, count=count)
        return count

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """Convert database row to MemoryEntry."""
        return MemoryEntry(
            id=row["id"],
            type=MemoryType(row["type"]),
            key=row["key"],
            value=row["value"],
            context=row["context"] or "",
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            access_count=row["access_count"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
        )


class PostgresMemory:
    """
    PostgreSQL-based persistent memory system.

    Uses async SQLAlchemy with the MemoryEntry ORM model from src.db.models.
    Same interface as PersistentMemory for drop-in replacement.
    """

    def __init__(self, user_id: int = 0) -> None:
        self.user_id = user_id
        logger.info("postgres_memory_initialized", user_id=user_id)

    async def store(
        self,
        type: MemoryType,
        key: str,
        value: str,
        context: str = "",
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
    ) -> int:
        """Store memory entry in PostgreSQL."""
        from ..db.database import get_session
        from ..db.models import MemoryEntry as DBMemoryEntry

        async with get_session() as session:
            # Upsert: check existing
            from sqlalchemy import select, and_
            result = await session.execute(
                select(DBMemoryEntry).where(
                    and_(
                        DBMemoryEntry.user_id == self.user_id,
                        DBMemoryEntry.key == key,
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.value = value
                existing.context = context
                existing.confidence = confidence
                existing.tags = tags or []
                existing.type = type.value
                existing.updated_at = datetime.now()
                entry_id = existing.id
            else:
                entry = DBMemoryEntry(
                    user_id=self.user_id,
                    type=type.value,
                    key=key,
                    value=value,
                    context=context,
                    confidence=confidence,
                    tags=tags or [],
                )
                session.add(entry)
                await session.flush()
                entry_id = entry.id

        logger.info("pg_memory_stored", key=key, type=type.value, id=entry_id)
        return entry_id

    async def retrieve(self, key: str) -> Optional[MemoryEntry]:
        """Retrieve memory entry by key from PostgreSQL."""
        from ..db.database import get_session
        from ..db.models import MemoryEntry as DBMemoryEntry
        from sqlalchemy import and_

        async with get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(DBMemoryEntry).where(
                    and_(
                        DBMemoryEntry.user_id == self.user_id,
                        DBMemoryEntry.key == key,
                    )
                )
            )
            db_entry = result.scalar_one_or_none()

            if not db_entry:
                return None

            db_entry.access_count += 1

            return MemoryEntry(
                id=db_entry.id,
                type=MemoryType(db_entry.type),
                key=db_entry.key,
                value=db_entry.value,
                context=db_entry.context or "",
                confidence=db_entry.confidence,
                created_at=db_entry.created_at,
                updated_at=db_entry.updated_at,
                access_count=db_entry.access_count,
                tags=db_entry.tags or [],
            )

    async def search(
        self,
        query: Optional[str] = None,
        type: Optional[MemoryType] = None,
        min_confidence: float = 0.0,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Search memory entries in PostgreSQL."""
        from ..db.database import get_session
        from ..db.models import MemoryEntry as DBMemoryEntry
        from sqlalchemy import select, or_

        async with get_session() as session:
            stmt = select(DBMemoryEntry).where(
                DBMemoryEntry.user_id == self.user_id,
                DBMemoryEntry.confidence >= min_confidence,
            )

            if type:
                stmt = stmt.where(DBMemoryEntry.type == type.value)

            if query:
                pattern = f"%{query}%"
                stmt = stmt.where(
                    or_(
                        DBMemoryEntry.key.ilike(pattern),
                        DBMemoryEntry.value.ilike(pattern),
                        DBMemoryEntry.context.ilike(pattern),
                    )
                )

            stmt = stmt.order_by(
                DBMemoryEntry.confidence.desc(),
                DBMemoryEntry.access_count.desc(),
            ).limit(limit)

            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            MemoryEntry(
                id=r.id,
                type=MemoryType(r.type),
                key=r.key,
                value=r.value,
                context=r.context or "",
                confidence=r.confidence,
                created_at=r.created_at,
                updated_at=r.updated_at,
                access_count=r.access_count,
                tags=r.tags or [],
            )
            for r in rows
        ]

    async def delete(self, key: str) -> bool:
        """Delete memory entry from PostgreSQL."""
        from ..db.database import get_session
        from ..db.models import MemoryEntry as DBMemoryEntry
        from sqlalchemy import and_, delete

        async with get_session() as session:
            result = await session.execute(
                delete(DBMemoryEntry).where(
                    and_(
                        DBMemoryEntry.user_id == self.user_id,
                        DBMemoryEntry.key == key,
                    )
                )
            )
            deleted = result.rowcount > 0

        if deleted:
            logger.info("pg_memory_deleted", key=key)
        return deleted

    async def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics from PostgreSQL."""
        from ..db.database import get_session
        from ..db.models import MemoryEntry as DBMemoryEntry
        from sqlalchemy import select, func

        async with get_session() as session:
            result = await session.execute(
                select(
                    func.count(DBMemoryEntry.id).label("total"),
                    func.avg(DBMemoryEntry.confidence).label("avg_confidence"),
                    func.sum(DBMemoryEntry.access_count).label("total_accesses"),
                ).where(DBMemoryEntry.user_id == self.user_id)
            )
            row = result.one()

        return {
            "total_entries": row.total or 0,
            "avg_confidence": round(row.avg_confidence or 0, 2),
            "total_accesses": row.total_accesses or 0,
        }


def create_memory(
    backend: str = "sqlite",
    user_id: int = 0,
    db_path: str = "agent_memory.db",
) -> PersistentMemory | PostgresMemory:
    """Factory function to create memory backend.

    Args:
        backend: "sqlite" or "postgresql"
        user_id: User ID for PostgreSQL backend
        db_path: Database path for SQLite backend

    Returns:
        Memory instance
    """
    if backend == "postgresql":
        return PostgresMemory(user_id=user_id)
    return PersistentMemory(db_path=db_path)
