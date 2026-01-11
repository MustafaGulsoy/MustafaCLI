"""
Tests for Parallel Execution
=============================

Tests for parallel tool execution system.
"""

import pytest
import asyncio
from pathlib import Path

from src.core.parallel import (
    ParallelExecutor,
    ParallelTask,
    TaskStatus,
    create_parallel_tool_calls,
)


class TestParallelExecutor:
    """Tests for ParallelExecutor."""

    @pytest.mark.asyncio
    async def test_simple_parallel_execution(self):
        """Test simple parallel execution."""
        executor = ParallelExecutor(max_workers=3)

        # Add independent tasks
        async def add(a, b):
            await asyncio.sleep(0.1)
            return a + b

        executor.add_task("task1", add, args=(1, 2))
        executor.add_task("task2", add, args=(3, 4))
        executor.add_task("task3", add, args=(5, 6))

        results = await executor.execute_all()

        assert len(results) == 3
        assert results["task1"] == 3
        assert results["task2"] == 7
        assert results["task3"] == 11

    @pytest.mark.asyncio
    async def test_dependent_tasks(self):
        """Test tasks with dependencies."""
        executor = ParallelExecutor(max_workers=5)

        results_store = {}

        async def task_a():
            await asyncio.sleep(0.1)
            results_store["a"] = 10
            return 10

        async def task_b():
            await asyncio.sleep(0.1)
            results_store["b"] = 20
            return 20

        async def task_c():
            # Depends on A and B
            await asyncio.sleep(0.1)
            return results_store["a"] + results_store["b"]

        executor.add_task("task_a", task_a)
        executor.add_task("task_b", task_b)
        executor.add_task("task_c", task_c, dependencies=["task_a", "task_b"])

        results = await executor.execute_all()

        assert results["task_a"] == 10
        assert results["task_b"] == 20
        assert results["task_c"] == 30

    @pytest.mark.asyncio
    async def test_task_failure(self):
        """Test handling of task failures."""
        executor = ParallelExecutor(max_workers=2)

        async def failing_task():
            await asyncio.sleep(0.1)
            raise ValueError("Test error")

        async def successful_task():
            await asyncio.sleep(0.1)
            return "success"

        executor.add_task("fail", failing_task)
        executor.add_task("success", successful_task)

        with pytest.raises(Exception):
            await executor.execute_all(fail_fast=True)

        # Check status
        status = executor.get_status()
        assert status["fail"] == TaskStatus.FAILED


class TestParallelToolCallGrouping:
    """Tests for tool call grouping."""

    def test_group_independent_reads(self):
        """Test grouping of independent read operations."""
        tool_calls = [
            {"name": "view", "arguments": {"path": "file1.txt"}},
            {"name": "view", "arguments": {"path": "file2.txt"}},
            {"name": "view", "arguments": {"path": "file3.txt"}},
        ]

        batches = create_parallel_tool_calls(tool_calls)

        # All reads should be in one batch
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_separate_write_operations(self):
        """Test that write operations are separated."""
        tool_calls = [
            {"name": "view", "arguments": {"path": "file1.txt"}},
            {"name": "str_replace", "arguments": {"path": "file1.txt"}},
            {"name": "view", "arguments": {"path": "file2.txt"}},
        ]

        batches = create_parallel_tool_calls(tool_calls)

        # Should have 3 batches: [view], [str_replace], [view]
        assert len(batches) == 3
        assert batches[0][0]["name"] == "view"
        assert batches[1][0]["name"] == "str_replace"
        assert batches[2][0]["name"] == "view"
