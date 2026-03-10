# MustafaCLI Full Upgrade Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all missing features: PostgreSQL persistence, JWT auth, full plugin system with entry-points + MCP, session persistence, API versioning, WebSocket reconnect, frontend UX, i18n, Windows compatibility, comprehensive tests, and E2E tests.

**Architecture:** Three-layer upgrade — database layer (PostgreSQL via asyncpg + SQLAlchemy async), auth layer (JWT + bcrypt), and plugin layer (entry-points + MCP protocol). All API endpoints move under `/api/v1/`. Frontend gets auth, reconnect, error handling, and i18n.

**Tech Stack:** Python 3.10+, PostgreSQL (asyncpg, SQLAlchemy async), FastAPI, JWT (python-jose, passlib), MCP (jsonrpc), Angular 17, Jasmine/Karma, Playwright (E2E)

---

## File Structure

### New Files
```
src/
├── db/
│   ├── __init__.py
│   ├── database.py          # AsyncPG + SQLAlchemy async engine
│   ├── models.py            # SQLAlchemy ORM models (User, Session, ChatMessage, Plugin, Memory)
│   └── migrations/
│       ├── env.py            # Alembic async config
│       └── versions/         # Migration files
├── auth/
│   ├── __init__.py
│   ├── jwt_handler.py        # JWT token creation/verification
│   ├── dependencies.py       # FastAPI auth dependencies (get_current_user)
│   ├── routes.py             # /api/v1/auth/register, login, refresh
│   └── password.py           # bcrypt password hashing
├── plugins/
│   ├── __init__.py
│   ├── base.py               # PluginBase ABC, @plugin decorator, PluginMetadata
│   ├── registry.py           # PluginRegistry with entry_points discovery
│   ├── loader.py             # Load plugins from dirs + entry_points
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── protocol.py       # MCP JSON-RPC protocol handler
│   │   ├── server.py         # MCP server (expose tools as MCP)
│   │   └── client.py         # MCP client (consume external MCP tools)
│   └── hooks.py              # Plugin lifecycle hooks
├── i18n/
│   ├── __init__.py
│   ├── translator.py         # Translation system
│   └── locales/
│       ├── en.json
│       └── tr.json
├── core/
│   └── platform.py           # Windows/Linux platform compatibility layer
tests/
├── test_auth.py
├── test_db.py
├── test_plugins.py
├── test_mcp.py
├── test_api_v1.py
├── test_sessions_persist.py
├── test_websocket.py
├── test_i18n.py
├── test_platform.py
├── e2e/
│   ├── conftest.py
│   ├── test_full_flow.py
│   └── test_auth_flow.py
frontend/
├── src/app/
│   ├── core/
│   │   ├── auth/
│   │   │   ├── auth.service.ts
│   │   │   ├── auth.guard.ts
│   │   │   ├── auth.interceptor.ts
│   │   │   └── login/login.component.ts
│   │   └── i18n/
│   │       ├── i18n.service.ts
│   │       └── i18n.pipe.ts
│   ├── services/
│   │   └── websocket.service.ts  # (modify: add reconnect)
│   └── components/
│       ├── chat/chat.component.ts  # (modify: error UI, i18n)
│       ├── file-tree/file-tree.component.ts
│       └── error-toast/error-toast.component.ts
```

### Modified Files
```
src/api/main.py              # API v1 router, auth middleware, PostgreSQL startup
src/api/models.py            # Add auth models, versioned schemas
src/api/sessions.py          # PostgreSQL-backed session persistence
src/core/skills.py           # Integrate with plugin system
src/core/memory.py           # PostgreSQL backend instead of SQLite
src/core/tools.py            # Platform-aware paths, plugin tool registration
src/core/config.py           # Add DB, auth, plugin settings
src/core/constants.py        # Add new constants
src/core/exceptions.py       # Add auth, plugin, MCP exceptions
requirements.txt             # Add new dependencies
pyproject.toml               # Add entry_points, new deps
```

---

## Chunk 1: Database Layer (PostgreSQL)

### Task 1: Add PostgreSQL Dependencies

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update requirements.txt**

Add to `requirements.txt`:
```
# Database
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.25
alembic==1.13.1

# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# MCP / Plugin
jsonrpcserver==5.0.9
jsonrpcclient==4.0.3
stevedore==5.2.0
```

- [ ] **Step 2: Update pyproject.toml dependencies**

Add to `[project.dependencies]`:
```toml
"asyncpg~=0.29.0",
"sqlalchemy[asyncio]~=2.0.25",
"alembic~=1.13.1",
"python-jose[cryptography]~=3.3.0",
"passlib[bcrypt]~=1.7.4",
```

Add entry_points section:
```toml
[project.entry-points."mustafacli.plugins"]
# Built-in plugins registered here
```

- [ ] **Step 3: Install dependencies**

Run: `pip install asyncpg sqlalchemy[asyncio] alembic python-jose[cryptography] passlib[bcrypt] jsonrpcserver jsonrpcclient stevedore`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt pyproject.toml
git commit -m "feat: add PostgreSQL, auth, and plugin dependencies"
```

### Task 2: Database Engine & Models

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/database.py`
- Create: `src/db/models.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write database test**

```python
# tests/test_db.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///test.db")
    yield engine
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_tables(db_engine):
    from src.db.models import Base
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Verify tables exist
    async with db_engine.begin() as conn:
        result = await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                __import__('sqlalchemy').text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        )
        table_names = [r[0] for r in result]
        assert "users" in table_names
        assert "sessions" in table_names
        assert "chat_messages" in table_names
        assert "plugins" in table_names
        assert "memory_entries" in table_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL (no module src.db)

- [ ] **Step 3: Create src/db/__init__.py**

```python
"""Database layer - PostgreSQL with async SQLAlchemy."""
```

- [ ] **Step 4: Create src/db/database.py**

```python
"""
Async database engine and session management.
Supports PostgreSQL (production) and SQLite (testing).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(database_url: str, echo: bool = False) -> AsyncEngine:
    """Initialize database engine."""
    global _engine, _session_factory
    _engine = create_async_engine(database_url, echo=echo, pool_size=10, max_overflow=20)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def close_db() -> None:
    """Close database engine."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    """Get current engine."""
    if not _engine:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    if not _session_factory:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables (for development)."""
    from .models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 5: Create src/db/models.py**

```python
"""
SQLAlchemy ORM models for PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum, Float,
    ForeignKey, Integer, String, Text, JSON,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    memory_entries = relationship("MemoryEntry", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), unique=True, nullable=False, index=True, default=lambda: str(uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    working_dir = Column(String(500), default=".")
    model_name = Column(String(100), default="qwen2.5-coder:32b")
    rag_enabled = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                          order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    tool_results = Column(JSON, nullable=True)
    tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("idx_session_created", "session_id", "created_at"),
    )


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(20), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    context = Column(Text, default="")
    confidence = Column(Float, default=1.0)
    access_count = Column(Integer, default=0)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="memory_entries")

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_memory_key"),
        Index("idx_memory_type", "type"),
        Index("idx_memory_confidence", "confidence"),
    )


class PluginRecord(Base):
    __tablename__ = "plugins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    version = Column(String(20), default="0.1.0")
    description = Column(Text, default="")
    plugin_type = Column(String(20), default="entry_point")  # entry_point, mcp, directory
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)
    installed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 6: Run test**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/db/ tests/test_db.py
git commit -m "feat: add PostgreSQL database layer with ORM models"
```

### Task 3: Alembic Migrations Setup

**Files:**
- Create: `alembic.ini`
- Create: `src/db/migrations/env.py`
- Create: `src/db/migrations/versions/`

- [ ] **Step 1: Initialize alembic**

Run: `cd D:/Private/Projeler/Python/MustafaCLI && alembic init src/db/migrations`

- [ ] **Step 2: Configure alembic.ini**

Set `sqlalchemy.url = postgresql+asyncpg://mustafa:password@localhost:5432/mustafacli`

- [ ] **Step 3: Update migrations/env.py for async**

Configure async engine, import models from `src.db.models`.

- [ ] **Step 4: Generate initial migration**

Run: `alembic revision --autogenerate -m "initial tables"`

- [ ] **Step 5: Commit**

```bash
git add alembic.ini src/db/migrations/
git commit -m "feat: add Alembic migration system"
```

---

## Chunk 2: Authentication System (JWT)

### Task 4: Auth Module

**Files:**
- Create: `src/auth/__init__.py`
- Create: `src/auth/password.py`
- Create: `src/auth/jwt_handler.py`
- Create: `src/auth/dependencies.py`
- Create: `src/auth/routes.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write auth tests**

```python
# tests/test_auth.py
import pytest
from src.auth.password import hash_password, verify_password
from src.auth.jwt_handler import create_access_token, decode_token

def test_password_hash():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)

def test_jwt_create_and_decode():
    token = create_access_token({"sub": "testuser", "user_id": 1})
    payload = decode_token(token)
    assert payload["sub"] == "testuser"
    assert payload["user_id"] == 1

def test_jwt_expired():
    token = create_access_token({"sub": "test"}, expires_minutes=-1)
    payload = decode_token(token)
    assert payload is None
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest tests/test_auth.py -v`

- [ ] **Step 3: Create password.py**

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

- [ ] **Step 4: Create jwt_handler.py**

```python
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
import os

SECRET_KEY = os.getenv("AGENT_JWT_SECRET", "change-me-in-production-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
```

- [ ] **Step 5: Create dependencies.py**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from .jwt_handler import decode_token
from ..db.database import get_session
from ..db.models import User
from sqlalchemy import select

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == payload["user_id"]))
        user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
```

- [ ] **Step 6: Create routes.py**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from ..db.database import get_session
from ..db.models import User
from .password import hash_password, verify_password
from .jwt_handler import create_access_token, create_refresh_token, decode_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest):
    async with get_session() as session:
        existing = await session.execute(select(User).where(User.username == req.username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Username already exists")
        user = User(username=req.username, email=req.email, hashed_password=hash_password(req.password))
        session.add(user)
        await session.flush()
        tokens = _create_tokens(user)
    return tokens

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    async with get_session() as session:
        result = await session.execute(select(User).where(User.username == req.username))
        user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return _create_tokens(user)

@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str):
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    async with get_session() as session:
        result = await session.execute(select(User).where(User.id == payload["user_id"]))
        user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return _create_tokens(user)

def _create_tokens(user: User) -> TokenResponse:
    data = {"sub": user.username, "user_id": user.id}
    return TokenResponse(
        access_token=create_access_token(data),
        refresh_token=create_refresh_token(data),
    )
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/auth/ tests/test_auth.py
git commit -m "feat: add JWT authentication system"
```

---

## Chunk 3: Full Plugin System (Entry-points + MCP)

### Task 5: Plugin Base & Registry

**Files:**
- Create: `src/plugins/__init__.py`
- Create: `src/plugins/base.py`
- Create: `src/plugins/registry.py`
- Create: `src/plugins/loader.py`
- Create: `src/plugins/hooks.py`
- Create: `tests/test_plugins.py`

- [ ] **Step 1: Write plugin tests**

```python
# tests/test_plugins.py
import pytest
from src.plugins.base import PluginBase, PluginMetadata, plugin_tool
from src.plugins.registry import PluginRegistry

class MockPlugin(PluginBase):
    metadata = PluginMetadata(
        name="mock-plugin",
        version="1.0.0",
        description="Test plugin",
        author="Test",
    )

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    @plugin_tool(name="mock_tool", description="A mock tool")
    async def mock_tool(self, query: str) -> str:
        return f"Mock result: {query}"

def test_plugin_metadata():
    p = MockPlugin()
    assert p.metadata.name == "mock-plugin"
    assert p.metadata.version == "1.0.0"

def test_plugin_tools():
    p = MockPlugin()
    tools = p.get_tools()
    assert len(tools) == 1
    assert tools[0].name == "mock_tool"

@pytest.mark.asyncio
async def test_plugin_registry():
    registry = PluginRegistry()
    registry.register(MockPlugin)
    assert "mock-plugin" in registry.list_plugins()
    await registry.initialize_all()
    tools = registry.get_all_tools()
    assert any(t.name == "mock_tool" for t in tools)
    await registry.shutdown_all()
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest tests/test_plugins.py -v`

- [ ] **Step 3: Create src/plugins/base.py**

```python
"""
Plugin base class and decorators.
Inspired by LangChain @tool, Auto-GPT plugins, and Python entry_points.
"""
from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..core.tools import Tool, ToolResult


@dataclass
class PluginMetadata:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    requires: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    license: str = "MIT"


def plugin_tool(name: str, description: str, parameters: dict | None = None):
    """Decorator to mark a method as a plugin tool."""
    def decorator(func: Callable):
        func._is_plugin_tool = True
        func._tool_name = name
        func._tool_description = description
        func._tool_parameters = parameters or _extract_params(func)
        return func
    return decorator


def _extract_params(func: Callable) -> dict:
    """Auto-extract parameters from function signature."""
    sig = inspect.signature(func)
    params = {}
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        param_type = "string"
        if param.annotation == int:
            param_type = "integer"
        elif param.annotation == bool:
            param_type = "boolean"
        elif param.annotation == float:
            param_type = "number"
        params[param_name] = {
            "type": param_type,
            "description": param_name,
            "required": param.default == inspect.Parameter.empty,
        }
    return params


class PluginTool(Tool):
    """Wraps a plugin method as an agent Tool."""

    def __init__(self, name: str, description: str, parameters: dict, func: Callable):
        self._name = name
        self._description = description
        self._parameters = parameters
        self._func = func

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            if inspect.iscoroutinefunction(self._func):
                result = await self._func(**kwargs)
            else:
                result = self._func(**kwargs)
            return ToolResult(success=True, output=str(result))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class PluginBase(ABC):
    """Base class for all plugins."""

    metadata: PluginMetadata

    @abstractmethod
    async def initialize(self) -> None:
        """Called when plugin is loaded."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Called when plugin is unloaded."""
        ...

    def get_tools(self) -> list[PluginTool]:
        """Discover and return all @plugin_tool methods."""
        tools = []
        for attr_name in dir(self):
            attr = getattr(self, attr_name, None)
            if callable(attr) and getattr(attr, "_is_plugin_tool", False):
                tools.append(PluginTool(
                    name=attr._tool_name,
                    description=attr._tool_description,
                    parameters=attr._tool_parameters,
                    func=attr,
                ))
        return tools

    def on_agent_start(self) -> None:
        """Hook: called when agent starts a task."""
        pass

    def on_agent_end(self) -> None:
        """Hook: called when agent completes a task."""
        pass

    def on_tool_call(self, tool_name: str, args: dict) -> dict:
        """Hook: called before a tool executes. Can modify args."""
        return args

    def on_tool_result(self, tool_name: str, result: ToolResult) -> ToolResult:
        """Hook: called after a tool executes. Can modify result."""
        return result
```

- [ ] **Step 4: Create src/plugins/registry.py**

```python
"""Plugin registry with entry_points discovery."""
from __future__ import annotations

from typing import Type
from .base import PluginBase, PluginTool
from ..core.logging_config import get_logger

logger = get_logger(__name__)


class PluginRegistry:
    """Manages plugin lifecycle and tool registration."""

    def __init__(self):
        self._plugin_classes: dict[str, Type[PluginBase]] = {}
        self._instances: dict[str, PluginBase] = {}

    def register(self, plugin_cls: Type[PluginBase]) -> None:
        name = plugin_cls.metadata.name
        self._plugin_classes[name] = plugin_cls
        logger.info("plugin_registered", name=name, version=plugin_cls.metadata.version)

    def unregister(self, name: str) -> None:
        self._plugin_classes.pop(name, None)
        self._instances.pop(name, None)

    def list_plugins(self) -> list[str]:
        return list(self._plugin_classes.keys())

    async def initialize_all(self) -> None:
        for name, cls in self._plugin_classes.items():
            if name not in self._instances:
                instance = cls()
                await instance.initialize()
                self._instances[name] = instance
                logger.info("plugin_initialized", name=name)

    async def shutdown_all(self) -> None:
        for name, instance in self._instances.items():
            await instance.shutdown()
            logger.info("plugin_shutdown", name=name)
        self._instances.clear()

    def get_all_tools(self) -> list[PluginTool]:
        tools = []
        for instance in self._instances.values():
            tools.extend(instance.get_tools())
        return tools

    def get_plugin(self, name: str) -> PluginBase | None:
        return self._instances.get(name)

    def fire_hook(self, hook_name: str, **kwargs):
        for instance in self._instances.values():
            hook = getattr(instance, hook_name, None)
            if hook and callable(hook):
                hook(**kwargs)
```

- [ ] **Step 5: Create src/plugins/loader.py**

```python
"""Load plugins from entry_points and directories."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Type

from .base import PluginBase, PluginMetadata
from .registry import PluginRegistry
from ..core.logging_config import get_logger

logger = get_logger(__name__)


def load_entry_point_plugins(registry: PluginRegistry) -> int:
    """Discover plugins via Python entry_points (pip installable)."""
    count = 0
    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points
        eps = entry_points(group="mustafacli.plugins")
    else:
        from importlib.metadata import entry_points
        eps = entry_points().get("mustafacli.plugins", [])

    for ep in eps:
        try:
            plugin_cls = ep.load()
            if isinstance(plugin_cls, type) and issubclass(plugin_cls, PluginBase):
                registry.register(plugin_cls)
                count += 1
                logger.info("entrypoint_plugin_loaded", name=ep.name)
        except Exception as e:
            logger.warning("entrypoint_plugin_failed", name=ep.name, error=str(e))
    return count


def load_directory_plugins(registry: PluginRegistry, plugins_dir: str) -> int:
    """Load plugins from a directory."""
    count = 0
    plugins_path = Path(plugins_dir)
    if not plugins_path.exists():
        return 0

    for plugin_dir in plugins_path.iterdir():
        if not plugin_dir.is_dir():
            continue
        init_file = plugin_dir / "__init__.py"
        if not init_file.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location(plugin_dir.name, str(init_file))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                register_fn = getattr(module, "register", None)
                if register_fn:
                    register_fn(registry)
                    count += 1
                    logger.info("directory_plugin_loaded", path=str(plugin_dir))
        except Exception as e:
            logger.warning("directory_plugin_failed", path=str(plugin_dir), error=str(e))
    return count


def load_all_plugins(
    registry: PluginRegistry,
    personal_dir: str = "~/.mustafacli/plugins",
    project_dir: str = ".mustafacli/plugins",
) -> int:
    """Load all plugins from all sources."""
    count = 0
    count += load_entry_point_plugins(registry)
    count += load_directory_plugins(registry, str(Path(personal_dir).expanduser()))
    count += load_directory_plugins(registry, project_dir)
    logger.info("all_plugins_loaded", total=count)
    return count
```

- [ ] **Step 6: Create src/plugins/hooks.py**

```python
"""Plugin lifecycle hooks."""
from __future__ import annotations

from enum import Enum


class HookEvent(str, Enum):
    AGENT_START = "on_agent_start"
    AGENT_END = "on_agent_end"
    TOOL_CALL = "on_tool_call"
    TOOL_RESULT = "on_tool_result"
    SESSION_CREATE = "on_session_create"
    SESSION_END = "on_session_end"
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_plugins.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/plugins/ tests/test_plugins.py
git commit -m "feat: add full plugin system with entry_points and directory discovery"
```

### Task 6: MCP Protocol Support

**Files:**
- Create: `src/plugins/mcp/__init__.py`
- Create: `src/plugins/mcp/protocol.py`
- Create: `src/plugins/mcp/server.py`
- Create: `src/plugins/mcp/client.py`
- Create: `tests/test_mcp.py`

- [ ] **Step 1: Write MCP tests**

```python
# tests/test_mcp.py
import pytest
from src.plugins.mcp.protocol import MCPMessage, MCPMethod

def test_mcp_message_serialize():
    msg = MCPMessage(method=MCPMethod.TOOLS_LIST, id="1")
    data = msg.to_dict()
    assert data["jsonrpc"] == "2.0"
    assert data["method"] == "tools/list"

def test_mcp_message_deserialize():
    data = {"jsonrpc": "2.0", "method": "tools/list", "id": "1", "params": {}}
    msg = MCPMessage.from_dict(data)
    assert msg.method == MCPMethod.TOOLS_LIST

@pytest.mark.asyncio
async def test_mcp_server_list_tools():
    from src.plugins.mcp.server import MCPServer
    from src.core.tools import create_default_tools
    registry = create_default_tools(".")
    server = MCPServer(registry)
    result = await server.handle_request({"jsonrpc": "2.0", "method": "tools/list", "id": "1", "params": {}})
    assert "result" in result
    assert "tools" in result["result"]
```

- [ ] **Step 2: Create protocol.py**

```python
"""MCP (Model Context Protocol) message types."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MCPMethod(str, Enum):
    INITIALIZE = "initialize"
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"


@dataclass
class MCPMessage:
    method: MCPMethod
    id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict:
        d = {"jsonrpc": self.jsonrpc, "method": self.method.value, "id": self.id}
        if self.params:
            d["params"] = self.params
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MCPMessage":
        method_str = data.get("method", "")
        method = MCPMethod(method_str) if method_str in [m.value for m in MCPMethod] else MCPMethod.INITIALIZE
        return cls(
            method=method,
            id=data.get("id", ""),
            params=data.get("params", {}),
            jsonrpc=data.get("jsonrpc", "2.0"),
        )


def make_response(id: str, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}

def make_error(id: str, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}
```

- [ ] **Step 3: Create server.py**

```python
"""MCP Server - expose MustafaCLI tools as MCP endpoints."""
from __future__ import annotations
from typing import Any
from ..mcp.protocol import MCPMessage, MCPMethod, make_response, make_error
from ...core.tools import ToolRegistry
from ...core.logging_config import get_logger

logger = get_logger(__name__)


class MCPServer:
    """Expose local tools via MCP protocol."""

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry

    async def handle_request(self, data: dict) -> dict:
        msg = MCPMessage.from_dict(data)
        handlers = {
            MCPMethod.INITIALIZE: self._handle_initialize,
            MCPMethod.TOOLS_LIST: self._handle_tools_list,
            MCPMethod.TOOLS_CALL: self._handle_tools_call,
        }
        handler = handlers.get(msg.method)
        if not handler:
            return make_error(msg.id, -32601, f"Method not found: {msg.method}")
        return await handler(msg)

    async def _handle_initialize(self, msg: MCPMessage) -> dict:
        return make_response(msg.id, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "mustafacli", "version": "0.4.0"},
            "capabilities": {"tools": {"listChanged": False}},
        })

    async def _handle_tools_list(self, msg: MCPMessage) -> dict:
        tools = []
        for defn in self.tool_registry.get_tool_definitions():
            tools.append({
                "name": defn["function"]["name"],
                "description": defn["function"].get("description", ""),
                "inputSchema": defn["function"].get("parameters", {}),
            })
        return make_response(msg.id, {"tools": tools})

    async def _handle_tools_call(self, msg: MCPMessage) -> dict:
        tool_name = msg.params.get("name", "")
        arguments = msg.params.get("arguments", {})
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            return make_error(msg.id, -32602, f"Tool not found: {tool_name}")
        result = await tool.execute(**arguments)
        return make_response(msg.id, {
            "content": [{"type": "text", "text": result.output}],
            "isError": not result.success,
        })
```

- [ ] **Step 4: Create client.py**

```python
"""MCP Client - consume external MCP tools."""
from __future__ import annotations
import json
import subprocess
import asyncio
from typing import Any
from ..base import PluginBase, PluginMetadata, PluginTool
from ...core.tools import ToolResult
from ...core.logging_config import get_logger

logger = get_logger(__name__)


class MCPClient:
    """Connect to external MCP servers via stdio."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        self.command = command
        self.env = env
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    async def connect(self) -> dict:
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
        )
        return await self._send({"method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "mustafacli", "version": "0.4.0"},
        }})

    async def list_tools(self) -> list[dict]:
        result = await self._send({"method": "tools/list", "params": {}})
        return result.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self._send({
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        contents = result.get("result", {}).get("content", [])
        return "\n".join(c.get("text", "") for c in contents if c.get("type") == "text")

    async def disconnect(self) -> None:
        if self._process:
            self._process.terminate()
            await self._process.wait()

    async def _send(self, data: dict) -> dict:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("Not connected")
        self._request_id += 1
        data["jsonrpc"] = "2.0"
        data["id"] = str(self._request_id)
        msg = json.dumps(data) + "\n"
        self._process.stdin.write(msg.encode())
        await self._process.stdin.drain()
        line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30)
        return json.loads(line.decode())
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_mcp.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/plugins/mcp/ tests/test_mcp.py
git commit -m "feat: add MCP protocol support (server + client)"
```

---

## Chunk 4: API v1, Session Persistence, Config Updates

### Task 7: Update Config & Constants

**Files:**
- Modify: `src/core/config.py`
- Modify: `src/core/constants.py`
- Modify: `src/core/exceptions.py`

- [ ] **Step 1: Add DB/Auth/Plugin settings to config.py**

Add to `AgentSettings`:
```python
# Database
database_url: str = "postgresql+asyncpg://mustafa:password@localhost:5432/mustafacli"

# Auth
jwt_secret: str = "change-me-in-production"
jwt_expire_minutes: int = 60

# Plugin
plugins_dir: str = "~/.mustafacli/plugins"
enable_mcp: bool = True

# i18n
default_locale: str = "en"
```

- [ ] **Step 2: Add new exceptions to exceptions.py**

```python
class AuthenticationError(AgentError):
    pass

class PluginError(AgentError):
    pass

class MCPError(AgentError):
    pass
```

- [ ] **Step 3: Commit**

```bash
git add src/core/config.py src/core/constants.py src/core/exceptions.py
git commit -m "feat: add DB, auth, plugin configuration and exceptions"
```

### Task 8: API v1 Router & Session Persistence

**Files:**
- Modify: `src/api/main.py`
- Modify: `src/api/sessions.py`
- Modify: `src/api/models.py`
- Create: `tests/test_api_v1.py`
- Create: `tests/test_sessions_persist.py`

- [ ] **Step 1: Write API v1 tests**

```python
# tests/test_api_v1.py
import pytest
from httpx import AsyncClient, ASGITransport
from src.api.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "version" in resp.json()

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_api_v1_prefix(client):
    resp = await client.get("/api/v1/sessions")
    # Should return 401 (auth required) not 404
    assert resp.status_code in [200, 401]
```

- [ ] **Step 2: Refactor main.py with API v1 router**

Move all `/api/` endpoints to `/api/v1/` using `APIRouter(prefix="/api/v1")`. Add auth router. Add database startup/shutdown lifecycle. Add auth middleware dependency.

- [ ] **Step 3: Update sessions.py for PostgreSQL persistence**

Replace in-memory dict with PostgreSQL-backed session storage. Load sessions from DB on startup. Save chat messages to DB.

- [ ] **Step 4: Update models.py with auth schemas**

Add `UserInfo`, `TokenResponse` to API models.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_api_v1.py tests/test_sessions_persist.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/ tests/test_api_v1.py tests/test_sessions_persist.py
git commit -m "feat: API v1 versioning and PostgreSQL session persistence"
```

---

## Chunk 5: i18n, Platform Compat, Memory Upgrade

### Task 9: i18n System

**Files:**
- Create: `src/i18n/__init__.py`
- Create: `src/i18n/translator.py`
- Create: `src/i18n/locales/en.json`
- Create: `src/i18n/locales/tr.json`
- Create: `tests/test_i18n.py`

- [ ] **Step 1: Write i18n tests**

```python
# tests/test_i18n.py
import pytest
from src.i18n.translator import Translator

def test_translate_en():
    t = Translator("en")
    assert t.t("welcome") == "Welcome to MustafaCLI"

def test_translate_tr():
    t = Translator("tr")
    assert t.t("welcome") == "MustafaCLI'ye hoş geldiniz"

def test_fallback_to_en():
    t = Translator("fr")  # Not supported
    assert t.t("welcome") == "Welcome to MustafaCLI"

def test_missing_key():
    t = Translator("en")
    assert t.t("nonexistent_key") == "nonexistent_key"
```

- [ ] **Step 2: Create translator.py**

```python
"""Simple i18n translation system."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

_LOCALES_DIR = Path(__file__).parent / "locales"
_cache: dict[str, dict] = {}


class Translator:
    def __init__(self, locale: str = "en"):
        self.locale = locale
        self._translations = self._load(locale)
        if locale != "en":
            self._fallback = self._load("en")
        else:
            self._fallback = {}

    def _load(self, locale: str) -> dict:
        if locale in _cache:
            return _cache[locale]
        path = _LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            return self._load("en") if locale != "en" else {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache[locale] = data
        return data

    def t(self, key: str, **kwargs) -> str:
        value = self._translations.get(key) or self._fallback.get(key) or key
        if kwargs:
            value = value.format(**kwargs)
        return value
```

- [ ] **Step 3: Create locale files**

en.json and tr.json with all UI strings.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_i18n.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/i18n/ tests/test_i18n.py
git commit -m "feat: add i18n translation system with EN/TR"
```

### Task 10: Platform Compatibility Layer

**Files:**
- Create: `src/core/platform.py`
- Create: `tests/test_platform.py`

- [ ] **Step 1: Write platform tests**

```python
# tests/test_platform.py
import pytest
from src.core.platform import normalize_path, get_shell_command, is_windows

def test_normalize_path():
    # Should handle both forward and back slashes
    result = normalize_path("C:\\Users\\test\\file.py")
    assert "\\" not in result or is_windows()

def test_shell_command():
    cmd = get_shell_command("echo hello")
    assert isinstance(cmd, list)
    assert len(cmd) >= 2
```

- [ ] **Step 2: Create platform.py**

```python
"""Platform compatibility layer for Windows/Linux/Mac."""
from __future__ import annotations
import os
import sys
import platform as _platform


def is_windows() -> bool:
    return sys.platform == "win32"

def is_linux() -> bool:
    return sys.platform.startswith("linux")

def is_mac() -> bool:
    return sys.platform == "darwin"

def normalize_path(path: str) -> str:
    return os.path.normpath(path)

def get_shell_command(cmd: str) -> list[str]:
    if is_windows():
        return ["cmd", "/c", cmd]
    return ["bash", "-c", cmd]

def get_home_dir() -> str:
    return os.path.expanduser("~")

def get_config_dir() -> str:
    if is_windows():
        return os.path.join(os.environ.get("APPDATA", get_home_dir()), "mustafacli")
    return os.path.join(get_home_dir(), ".mustafacli")

def get_null_device() -> str:
    return "NUL" if is_windows() else "/dev/null"
```

- [ ] **Step 3: Run tests & Commit**

```bash
git add src/core/platform.py tests/test_platform.py
git commit -m "feat: add cross-platform compatibility layer"
```

### Task 11: Memory System PostgreSQL Upgrade

**Files:**
- Modify: `src/core/memory.py`
- Create: `tests/test_memory_pg.py`

- [ ] **Step 1: Update PersistentMemory to support PostgreSQL**

Add `PostgresMemory` class alongside existing `PersistentMemory` (SQLite). Use `src/db/models.py` `MemoryEntry` ORM model. Factory function `create_memory(backend="postgresql"|"sqlite")`.

- [ ] **Step 2: Write tests & Commit**

```bash
git add src/core/memory.py tests/test_memory_pg.py
git commit -m "feat: upgrade memory system to support PostgreSQL"
```

---

## Chunk 6: Skills Integration with Plugin System

### Task 12: Upgrade Skills to Use Plugin System

**Files:**
- Modify: `src/core/skills.py`

- [ ] **Step 1: Add plugin-aware skill loading**

Integrate `PluginRegistry` into `SkillRegistry`. Plugin tools get auto-registered as skills. SKILL.md files from plugin directories also get loaded.

- [ ] **Step 2: Commit**

```bash
git add src/core/skills.py
git commit -m "feat: integrate skills with plugin system"
```

---

## Chunk 7: Frontend Upgrades

### Task 13: Frontend Auth System

**Files:**
- Create: `frontend/src/app/core/auth/auth.service.ts`
- Create: `frontend/src/app/core/auth/auth.guard.ts`
- Create: `frontend/src/app/core/auth/auth.interceptor.ts`
- Create: `frontend/src/app/core/auth/login/login.component.ts`
- Create: `frontend/src/app/core/auth/login/login.component.html`

Auth service with JWT token storage, auto-refresh, login/register forms, route guards, HTTP interceptor for Authorization header.

### Task 14: WebSocket Reconnect

**Files:**
- Modify: `frontend/src/app/services/websocket.service.ts`

Add exponential backoff reconnect, connection state observable, heartbeat/ping mechanism, max retry limit.

### Task 15: Error Toast Component

**Files:**
- Create: `frontend/src/app/components/error-toast/error-toast.component.ts`

Global error handler, toast notifications, user-friendly error messages.

### Task 16: File Tree Component

**Files:**
- Create: `frontend/src/app/components/file-tree/file-tree.component.ts`

Tree view of working directory, file click to view, lazy loading.

### Task 17: Frontend i18n

**Files:**
- Create: `frontend/src/app/core/i18n/i18n.service.ts`
- Create: `frontend/src/app/core/i18n/i18n.pipe.ts`

Translation pipe, locale switching, sync with backend locale files.

### Task 18: Frontend Tests

**Files:**
- Create: `frontend/src/app/core/auth/auth.service.spec.ts`
- Create: `frontend/src/app/services/websocket.service.spec.ts`
- Create: `frontend/src/app/components/chat/chat.component.spec.ts`

Jasmine/Karma unit tests for all services and components.

- [ ] **Commit all frontend changes**

```bash
git add frontend/
git commit -m "feat: frontend auth, reconnect, error UI, file tree, i18n, tests"
```

---

## Chunk 8: E2E Tests & WebSocket Tests

### Task 19: Backend WebSocket Tests

**Files:**
- Create: `tests/test_websocket.py`

Test WebSocket connection, message flow, reconnection handling, auth on WS.

### Task 20: E2E Tests

**Files:**
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_full_flow.py`
- Create: `tests/e2e/test_auth_flow.py`

Full flow: register → login → create session → send message → get response → delete session. Auth flow: register, login, refresh, invalid token.

- [ ] **Commit**

```bash
git add tests/
git commit -m "feat: add WebSocket and E2E tests"
```

---

## Chunk 9: Final Integration & Docker Update

### Task 21: Update Docker & Deployment

**Files:**
- Modify: `deployment/Dockerfile`
- Modify: `deployment/docker-compose.yml`

Add PostgreSQL service, environment variables, health checks, volume for DB persistence.

### Task 22: Update CI/CD

**Files:**
- Modify: `.github/workflows/ci.yml`

Add PostgreSQL service for tests, E2E test step, plugin test step.

### Task 23: Final Integration Test

- [ ] Run all tests: `pytest -v --cov=src`
- [ ] Verify all endpoints work with auth
- [ ] Verify plugin loading
- [ ] Verify MCP protocol
- [ ] Verify session persistence across restart

- [ ] **Final commit**

```bash
git add .
git commit -m "feat: complete full upgrade - PostgreSQL, auth, plugins, MCP, i18n, tests"
```
