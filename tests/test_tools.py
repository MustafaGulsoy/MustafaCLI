"""
Tests for Tool System
=====================

Comprehensive tests for all tools including security.
"""

import pytest
from pathlib import Path

from src.core.tools import (
    BashTool,
    ViewTool,
    StrReplaceTool,
    CreateFileTool,
    ToolResult,
)
from src.core.exceptions import PathTraversalError, CommandBlockedError, SecurityError


class TestBashTool:
    """Tests for BashTool."""

    @pytest.mark.asyncio
    async def test_simple_command(self, temp_dir: Path):
        """Test simple safe command execution."""
        tool = BashTool(working_dir=str(temp_dir), allow_dangerous=False)
        result = await tool.execute("echo 'hello world'")

        assert result.success
        assert "hello world" in result.output

    @pytest.mark.asyncio
    async def test_blocked_command(self, temp_dir: Path):
        """Test that dangerous commands are blocked."""
        tool = BashTool(working_dir=str(temp_dir), allow_dangerous=False)
        result = await tool.execute("rm -rf /")

        assert not result.success
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_whitelist_enforcement(self, temp_dir: Path):
        """Test command whitelist enforcement."""
        tool = BashTool(working_dir=str(temp_dir), allow_dangerous=False)
        result = await tool.execute("dangerous_command")

        assert not result.success
        assert "whitelist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_timeout(self, temp_dir: Path):
        """Test command timeout."""
        tool = BashTool(working_dir=str(temp_dir), timeout=1)
        # Use platform-independent sleep command
        import sys
        if sys.platform == "win32":
            result = await tool.execute('python -c "import time; time.sleep(10)"')
        else:
            result = await tool.execute("python -c 'import time; time.sleep(10)'")

        assert not result.success
        assert "timeout" in result.error.lower()


class TestViewTool:
    """Tests for ViewTool."""

    @pytest.mark.asyncio
    async def test_view_file(self, temp_dir: Path):
        """Test viewing a file."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3")

        tool = ViewTool(working_dir=str(temp_dir))
        result = await tool.execute("test.txt")

        assert result.success
        assert "line 1" in result.output
        assert "line 2" in result.output

    @pytest.mark.asyncio
    async def test_view_directory(self, temp_dir: Path):
        """Test viewing directory structure."""
        (temp_dir / "file1.txt").touch()
        (temp_dir / "file2.txt").touch()

        tool = ViewTool(working_dir=str(temp_dir))
        result = await tool.execute(".")

        assert result.success
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, temp_dir: Path):
        """Test that path traversal is blocked."""
        tool = ViewTool(working_dir=str(temp_dir))
        result = await tool.execute("../../../etc/passwd")

        assert not result.success
        assert "traversal" in result.error.lower()


class TestStrReplaceTool:
    """Tests for StrReplaceTool."""

    @pytest.mark.asyncio
    async def test_simple_replace(self, temp_dir: Path):
        """Test simple string replacement."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("hello world")

        tool = StrReplaceTool(working_dir=str(temp_dir))
        result = await tool.execute(
            path="test.txt",
            old_str="hello",
            new_str="goodbye"
        )

        assert result.success
        assert test_file.read_text() == "goodbye world"

    @pytest.mark.asyncio
    async def test_string_not_found(self, temp_dir: Path):
        """Test error when string not found."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("hello world")

        tool = StrReplaceTool(working_dir=str(temp_dir))
        result = await tool.execute(
            path="test.txt",
            old_str="nonexistent",
            new_str="replacement"
        )

        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_non_unique_string(self, temp_dir: Path):
        """Test error when string appears multiple times."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("hello hello")

        tool = StrReplaceTool(working_dir=str(temp_dir))
        result = await tool.execute(
            path="test.txt",
            old_str="hello",
            new_str="goodbye"
        )

        assert not result.success
        assert "unique" in result.error.lower()


class TestCreateFileTool:
    """Tests for CreateFileTool."""

    @pytest.mark.asyncio
    async def test_create_file(self, temp_dir: Path):
        """Test creating a new file."""
        tool = CreateFileTool(working_dir=str(temp_dir))
        result = await tool.execute(
            path="new_file.txt",
            content="test content"
        )

        assert result.success
        assert (temp_dir / "new_file.txt").read_text() == "test content"

    @pytest.mark.asyncio
    async def test_file_already_exists(self, temp_dir: Path):
        """Test error when file already exists."""
        test_file = temp_dir / "existing.txt"
        test_file.write_text("original")

        tool = CreateFileTool(working_dir=str(temp_dir))
        result = await tool.execute(
            path="existing.txt",
            content="new content",
            overwrite=False
        )

        assert not result.success
        assert "exists" in result.error.lower()

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, temp_dir: Path):
        """Test that path traversal is blocked."""
        tool = CreateFileTool(working_dir=str(temp_dir))
        result = await tool.execute(
            path="../../../tmp/malicious.txt",
            content="bad content"
        )

        assert not result.success
        assert "traversal" in result.error.lower()
