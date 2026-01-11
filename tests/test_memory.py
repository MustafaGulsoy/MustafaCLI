"""
Tests for Memory System
========================

Tests for persistent memory management.
"""

import pytest
import tempfile
from pathlib import Path

from src.core.memory import (
    PersistentMemory,
    MemoryType,
    MemoryEntry,
)


class TestPersistentMemory:
    """Tests for PersistentMemory."""

    @pytest.fixture
    def memory(self, tmp_path):
        """Create temporary memory database."""
        db_path = tmp_path / "test_memory.db"
        return PersistentMemory(str(db_path))

    def test_store_and_retrieve(self, memory):
        """Test storing and retrieving memory."""
        memory.store(
            type=MemoryType.FACT,
            key="test_key",
            value="test_value",
            context="test context",
        )

        entry = memory.retrieve("test_key")
        assert entry is not None
        assert entry.key == "test_key"
        assert entry.value == "test_value"
        assert entry.type == MemoryType.FACT

    def test_retrieve_nonexistent(self, memory):
        """Test retrieving non-existent key."""
        entry = memory.retrieve("nonexistent")
        assert entry is None

    def test_update_existing(self, memory):
        """Test updating existing entry."""
        memory.store(
            type=MemoryType.FACT,
            key="test_key",
            value="value1",
        )

        # Update
        memory.store(
            type=MemoryType.FACT,
            key="test_key",
            value="value2",
        )

        entry = memory.retrieve("test_key")
        assert entry.value == "value2"

    def test_search_by_query(self, memory):
        """Test searching by query."""
        memory.store(MemoryType.FACT, "key1", "python programming")
        memory.store(MemoryType.FACT, "key2", "java programming")
        memory.store(MemoryType.FACT, "key3", "web development")

        results = memory.search(query="programming")
        assert len(results) == 2

    def test_search_by_type(self, memory):
        """Test searching by type."""
        memory.store(MemoryType.FACT, "fact1", "value1")
        memory.store(MemoryType.PREFERENCE, "pref1", "value2")
        memory.store(MemoryType.FACT, "fact2", "value3")

        results = memory.search(type=MemoryType.FACT)
        assert len(results) == 2
        assert all(e.type == MemoryType.FACT for e in results)

    def test_confidence_filtering(self, memory):
        """Test filtering by confidence."""
        memory.store(MemoryType.FACT, "high", "value1", confidence=0.9)
        memory.store(MemoryType.FACT, "medium", "value2", confidence=0.5)
        memory.store(MemoryType.FACT, "low", "value3", confidence=0.3)

        results = memory.search(min_confidence=0.7)
        assert len(results) == 1
        assert results[0].key == "high"

    def test_update_confidence(self, memory):
        """Test updating confidence score."""
        memory.store(MemoryType.FACT, "test", "value", confidence=0.5)

        memory.update_confidence("test", 0.9)

        entry = memory.retrieve("test")
        assert entry.confidence == 0.9

    def test_delete(self, memory):
        """Test deleting entry."""
        memory.store(MemoryType.FACT, "test", "value")

        deleted = memory.delete("test")
        assert deleted

        entry = memory.retrieve("test")
        assert entry is None

    def test_access_count(self, memory):
        """Test access counting."""
        memory.store(MemoryType.FACT, "test", "value")

        # Retrieve multiple times
        memory.retrieve("test")
        memory.retrieve("test")
        entry = memory.retrieve("test")

        assert entry.access_count == 3

    def test_get_stats(self, memory):
        """Test statistics."""
        memory.store(MemoryType.FACT, "fact1", "value1")
        memory.store(MemoryType.PREFERENCE, "pref1", "value2")
        memory.store(MemoryType.PATTERN, "pattern1", "value3")

        stats = memory.get_stats()
        assert stats["total_entries"] == 3
        assert stats["facts"] == 1
        assert stats["preferences"] == 1
        assert stats["patterns"] == 1

    def test_clear_all(self, memory):
        """Test clearing all entries."""
        memory.store(MemoryType.FACT, "key1", "value1")
        memory.store(MemoryType.FACT, "key2", "value2")

        count = memory.clear()
        assert count == 2

        stats = memory.get_stats()
        assert stats["total_entries"] == 0

    def test_clear_by_type(self, memory):
        """Test clearing by type."""
        memory.store(MemoryType.FACT, "fact1", "value1")
        memory.store(MemoryType.PREFERENCE, "pref1", "value2")

        count = memory.clear(type=MemoryType.FACT)
        assert count == 1

        stats = memory.get_stats()
        assert stats["total_entries"] == 1
        assert stats["facts"] == 0
        assert stats["preferences"] == 1

    def test_export_import_json(self, memory, tmp_path):
        """Test JSON export/import."""
        # Store data
        memory.store(MemoryType.FACT, "key1", "value1")
        memory.store(MemoryType.PREFERENCE, "key2", "value2")

        # Export
        export_path = tmp_path / "export.json"
        memory.export_json(str(export_path))
        assert export_path.exists()

        # Clear and import
        memory.clear()
        count = memory.import_json(str(export_path))
        assert count == 2

        # Verify
        entry = memory.retrieve("key1")
        assert entry is not None
        assert entry.value == "value1"
