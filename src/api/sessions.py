"""
Session Management
==================

Manage agent sessions for multi-user support.

Each session has its own:
- Agent instance
- Context
- Configuration

Author: Mustafa (Kardelen Yazılım)
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
import uuid

from ..core.agent import Agent, AgentConfig
from ..core.providers import create_provider
from ..core.tools import create_default_tools
from .models import SessionInfo


@dataclass
class Session:
    """Agent session"""
    session_id: str
    agent: Agent
    provider: any  # ModelProvider
    created_at: datetime
    working_dir: str
    rag_enabled: bool
    active: bool = True

    def to_info(self) -> SessionInfo:
        """Convert to SessionInfo"""
        return SessionInfo(
            session_id=self.session_id,
            created_at=self.created_at,
            working_dir=self.working_dir,
            rag_enabled=self.rag_enabled,
            active=self.active
        )


class SessionManager:
    """
    Manage multiple agent sessions

    Supports:
    - Creating sessions
    - Listing sessions
    - Deleting sessions
    - Session cleanup
    """

    def __init__(self, max_sessions: int = 10):
        self.max_sessions = max_sessions
        self.sessions: Dict[str, Session] = {}

    async def create_session(
        self,
        working_dir: str = ".",
        enable_rag: bool = False,
        model_name: str = "qwen2.5-coder:7b"
    ) -> Session:
        """
        Create new session

        Args:
            working_dir: Working directory for agent
            enable_rag: Enable RAG for this session
            model_name: Model to use

        Returns:
            Session object
        """
        # Check limit
        if len(self.sessions) >= self.max_sessions:
            # Remove oldest session
            oldest_id = min(
                self.sessions.keys(),
                key=lambda k: self.sessions[k].created_at
            )
            await self.delete_session(oldest_id)

        # Create session ID
        session_id = str(uuid.uuid4())

        # Create agent config
        config = AgentConfig(
            model_name=model_name,
            working_dir=working_dir,
            max_iterations=20,
            temperature=0.1,
        )

        # Create provider
        provider = create_provider(
            provider_type="ollama",
            model=model_name
        )

        # Create tools
        tools = create_default_tools(working_dir)

        # Create agent
        if enable_rag:
            try:
                from ..rag.integration import RAGAgent, RAGConfig

                rag_config = RAGConfig(
                    enabled=True,
                    db_path=".rag_db",
                    max_results=3,
                    min_score=0.5
                )

                agent = RAGAgent(
                    config=config,
                    provider=provider,
                    tool_registry=tools,
                    rag_config=rag_config
                )
            except Exception as e:
                print(f"RAG not available: {e}, using standard agent")
                agent = Agent(
                    config=config,
                    provider=provider,
                    tool_registry=tools
                )
        else:
            agent = Agent(
                config=config,
                provider=provider,
                tool_registry=tools
            )

        # Create session
        session = Session(
            session_id=session_id,
            agent=agent,
            provider=provider,
            created_at=datetime.now(),
            working_dir=working_dir,
            rag_enabled=enable_rag,
            active=True
        )

        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        return self.sessions.get(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        session = self.sessions.get(session_id)
        if not session:
            return False

        # Cleanup
        session.active = False
        try:
            await session.provider.close()
        except:
            pass

        # Remove from dict
        del self.sessions[session_id]
        return True

    def list_sessions(self) -> list[Session]:
        """List all sessions"""
        return list(self.sessions.values())
