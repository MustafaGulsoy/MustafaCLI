"""
Pytest Configuration and Fixtures
==================================

Shared fixtures for all tests.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
from pytest_mock import MockerFixture

from src.core.agent import Agent, AgentConfig
from src.core.context import ContextManager
from src.core.providers import OllamaProvider
from src.core.tools import ToolRegistry, BashTool, ViewTool, StrReplaceTool, CreateFileTool


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def agent_config(temp_dir: Path) -> AgentConfig:
    """Create test agent configuration."""
    return AgentConfig(
        model_name="test-model",
        working_dir=str(temp_dir),
        max_iterations=10,
        max_consecutive_tool_calls=5,
    )


@pytest.fixture
def context_manager() -> ContextManager:
    """Create test context manager."""
    return ContextManager(
        max_tokens=1000,
        reserve_tokens=100,
    )


@pytest.fixture
def tool_registry(temp_dir: Path) -> ToolRegistry:
    """Create test tool registry."""
    registry = ToolRegistry()
    registry.register(BashTool(working_dir=str(temp_dir), allow_dangerous=False))
    registry.register(ViewTool(working_dir=str(temp_dir)))
    registry.register(StrReplaceTool(working_dir=str(temp_dir)))
    registry.register(CreateFileTool(working_dir=str(temp_dir)))
    return registry


@pytest.fixture
def mock_provider(mocker: MockerFixture) -> OllamaProvider:
    """Create mock provider for testing."""
    provider = mocker.Mock(spec=OllamaProvider)
    provider.name = "mock"
    provider.supports_tools = True
    provider.supports_streaming = False
    return provider
