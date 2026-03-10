"""
Session Management - PostgreSQL Backed
========================================

Manage agent sessions with PostgreSQL persistence.
In-memory cache for active sessions, database for persistence.

Author: Mustafa (Kardelen Yazilim)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from sqlalchemy import select

from ..core.agent import Agent, AgentConfig
from ..core.providers import create_provider
from ..core.tools import create_default_tools
from ..db.database import get_session as get_db_session
from ..db.models import ChatMessage, ChatSession
from .models import SessionInfo


@dataclass
class Session:
    """Active agent session."""

    session_id: str
    agent: Agent
    provider: object  # ModelProvider
    created_at: datetime
    working_dir: str
    rag_enabled: bool
    user_id: int
    active: bool = True
    db_session_id: Optional[int] = None  # DB primary key

    def to_info(self) -> SessionInfo:
        return SessionInfo(
            session_id=self.session_id,
            created_at=self.created_at,
            working_dir=self.working_dir,
            rag_enabled=self.rag_enabled,
            active=self.active,
        )


class SessionManager:
    """Manage multiple agent sessions with PostgreSQL persistence."""

    def __init__(self, max_sessions: int = 10) -> None:
        self.max_sessions = max_sessions
        self.sessions: Dict[str, Session] = {}

    async def create_session(
        self,
        working_dir: str = ".",
        enable_rag: bool = False,
        model_name: str = "qwen2.5-coder:7b",
        user_id: int = 0,
    ) -> Session:
        """Create new session and persist to database."""
        # Enforce session limit
        if len(self.sessions) >= self.max_sessions:
            oldest_id = min(
                self.sessions.keys(),
                key=lambda k: self.sessions[k].created_at,
            )
            await self.delete_session(oldest_id)

        session_id = str(uuid4())

        # Persist to database
        db_id = None
        try:
            async with get_db_session() as db:
                db_session = ChatSession(
                    session_id=session_id,
                    user_id=user_id,
                    working_dir=working_dir,
                    model_name=model_name,
                    rag_enabled=enable_rag,
                    is_active=True,
                )
                db.add(db_session)
                await db.flush()
                db_id = db_session.id
        except Exception:
            # Continue without DB if not available (dev mode)
            pass

        # Create agent
        config = AgentConfig(
            model_name=model_name,
            working_dir=working_dir,
            max_iterations=20,
            temperature=0.1,
        )
        provider = create_provider(provider_type="ollama", model=model_name)
        tools = create_default_tools(working_dir)

        if enable_rag:
            try:
                from ..rag.integration import RAGAgent, RAGConfig

                rag_config = RAGConfig(
                    enabled=True, db_path=".rag_db", max_results=3, min_score=0.5
                )
                agent = RAGAgent(
                    config=config,
                    provider=provider,
                    tool_registry=tools,
                    rag_config=rag_config,
                )
            except Exception:
                agent = Agent(config=config, provider=provider, tool_registry=tools)
        else:
            agent = Agent(config=config, provider=provider, tool_registry=tools)

        session = Session(
            session_id=session_id,
            agent=agent,
            provider=provider,
            created_at=datetime.now(),
            working_dir=working_dir,
            rag_enabled=enable_rag,
            user_id=user_id,
            active=True,
            db_session_id=db_id,
        )
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID from memory cache."""
        return self.sessions.get(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete session from memory and database."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.active = False

        # Update database
        try:
            async with get_db_session() as db:
                result = await db.execute(
                    select(ChatSession).where(
                        ChatSession.session_id == session_id
                    )
                )
                db_session = result.scalar_one_or_none()
                if db_session:
                    db_session.is_active = False
        except Exception:
            pass

        # Cleanup provider
        try:
            await session.provider.close()
        except Exception:
            pass

        del self.sessions[session_id]
        return True

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list | None = None,
        tool_results: list | None = None,
        tokens_used: int = 0,
    ) -> None:
        """Save a chat message to the database."""
        session = self.sessions.get(session_id)
        if not session or not session.db_session_id:
            return

        try:
            async with get_db_session() as db:
                msg = ChatMessage(
                    session_id=session.db_session_id,
                    role=role,
                    content=content,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    tokens_used=tokens_used,
                )
                db.add(msg)
        except Exception:
            pass

    async def get_session_history(self, session_id: str) -> list[dict]:
        """Get chat history from database."""
        session = self.sessions.get(session_id)
        if not session or not session.db_session_id:
            return []

        try:
            async with get_db_session() as db:
                result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session.db_session_id)
                    .order_by(ChatMessage.created_at)
                )
                messages = result.scalars().all()
                return [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "tool_calls": msg.tool_calls,
                        "tool_results": msg.tool_results,
                        "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    }
                    for msg in messages
                ]
        except Exception:
            return []

    def list_sessions(self) -> list[Session]:
        return list(self.sessions.values())
