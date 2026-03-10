"""
FastAPI Main Application - v1 API
==================================

Web API for MustafaCLI with real-time WebSocket streaming.

Features:
- Versioned REST API (/api/v1/)
- JWT Authentication
- PostgreSQL session persistence
- WebSocket for real-time agent streaming
- CORS for Angular frontend
- Health checks

Author: Mustafa (Kardelen Yazilim)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import httpx
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from ..auth.dependencies import get_current_user
from ..auth.routes import router as auth_router
from ..core.agent import Agent, AgentConfig
from ..core.providers import create_provider
from ..core.tools import create_default_tools
from ..db.database import close_db, create_tables, init_db
from ..db.models import User
from .models import (
    AgentStatus,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SessionInfo,
)
from .sessions import SessionManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    import os

    db_url = os.getenv(
        "AGENT_DATABASE_URL",
        "postgresql+asyncpg://mustafa:password@localhost:5432/mustafacli",
    )
    await init_db(db_url)
    await create_tables()
    print("MustafaCLI API v0.5.0 started")
    print("API: http://localhost:8000/docs")
    print("WebSocket: ws://localhost:8000/ws/{session_id}")
    yield
    await close_db()
    print("MustafaCLI API shutting down...")


# Create FastAPI app
app = FastAPI(
    title="MustafaCLI API",
    description="AI Coding Agent API with real-time streaming",
    version="0.5.0",
    lifespan=lifespan,
)

# CORS configuration for Angular
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session manager (in-memory cache, backed by PostgreSQL)
session_manager = SessionManager()

# Active WebSocket connections
active_connections: Dict[str, WebSocket] = {}

# --- Auth Router (no auth required) ---
app.include_router(auth_router)

# --- API v1 Router (auth required) ---
v1_router = APIRouter(prefix="/api/v1", tags=["v1"])


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": "MustafaCLI API",
        "version": "0.5.0",
        "status": "running",
        "docs": "/docs",
        "api": "/api/v1",
        "websocket": "/ws/{session_id}",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint (no auth required)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:11434/api/tags", timeout=2
            )
            ollama_status = response.status_code == 200
    except Exception:
        ollama_status = False

    rag_status = Path(".rag_db").exists()

    return HealthResponse(
        status="healthy" if ollama_status else "degraded",
        ollama_connected=ollama_status,
        rag_available=rag_status,
        active_sessions=len(session_manager.sessions),
        timestamp=datetime.now(),
    )


# --- Session endpoints ---


@v1_router.post("/sessions", response_model=SessionInfo, status_code=201)
async def create_session(
    working_dir: str = ".",
    enable_rag: bool = False,
    user: User = Depends(get_current_user),
) -> SessionInfo:
    """Create new agent session."""
    try:
        session = await session_manager.create_session(
            working_dir=working_dir,
            enable_rag=enable_rag,
            user_id=user.id,
        )
        return session.to_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@v1_router.get("/sessions", response_model=List[SessionInfo])
async def list_sessions(
    user: User = Depends(get_current_user),
) -> list[SessionInfo]:
    """List user's active sessions."""
    return [
        s.to_info()
        for s in session_manager.sessions.values()
        if s.user_id == user.id
    ]


@v1_router.get("/sessions/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> SessionInfo:
    """Get session info."""
    session = session_manager.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_info()


@v1_router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Delete session."""
    session = session_manager.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    success = await session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete session")
    return {"status": "deleted", "session_id": session_id}


# --- Chat endpoint ---


@v1_router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: User = Depends(get_current_user),
) -> ChatResponse:
    """Send message to agent (non-streaming). Use WebSocket for streaming."""
    session = session_manager.get_session(request.session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        responses = []
        async for response in session.agent.run(request.message):
            responses.append(response)

        final = responses[-1] if responses else None
        if not final:
            raise HTTPException(status_code=500, detail="No response from agent")

        return ChatResponse(
            content=final.content,
            state=final.state.value,
            iteration=final.iteration,
            tool_calls=final.tool_calls or [],
            tool_results=[
                {
                    "name": tr.get("name", ""),
                    "success": tr.get("success", False),
                    "output": tr.get("output", ""),
                }
                for tr in (final.tool_results or [])
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Status endpoint ---


@v1_router.get("/status", response_model=AgentStatus)
async def get_agent_status(
    session_id: str,
    user: User = Depends(get_current_user),
) -> AgentStatus:
    """Get current agent status."""
    session = session_manager.get_session(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    return AgentStatus(
        state=session.agent.state.value,
        current_iteration=session.agent.current_iteration,
        max_iterations=session.agent.config.max_iterations,
    )


# Include v1 router
app.include_router(v1_router)


# --- WebSocket (token auth via query param) ---


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time streaming.

    Authentication: pass token as query param ?token=<jwt>

    Protocol:
    - Client sends: {"type": "message", "content": "..."}
    - Server sends: {"type": "response", "data": {...}}
    - Server sends: {"type": "complete", "data": {...}}
    - Server sends: {"type": "error", "error": "..."}
    """
    # Authenticate via query param
    token = websocket.query_params.get("token")
    if token:
        from ..auth.jwt_handler import decode_token

        payload = decode_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid token")
            return
    # Allow unauthenticated WebSocket for backward compatibility

    await websocket.accept()
    active_connections[session_id] = websocket

    try:
        session = session_manager.get_session(session_id)
        if not session:
            await websocket.send_json(
                {"type": "error", "error": "Session not found. Create session first."}
            )
            await websocket.close()
            return

        await websocket.send_json(
            {
                "type": "connected",
                "session_id": session_id,
                "working_dir": session.working_dir,
                "rag_enabled": session.rag_enabled,
            }
        )

        while True:
            data = await websocket.receive_json()

            if data.get("type") == "message":
                message = data.get("content", "")
                if not message:
                    await websocket.send_json(
                        {"type": "error", "error": "Empty message"}
                    )
                    continue

                try:
                    async for response in session.agent.run(message):
                        await websocket.send_json(
                            {
                                "type": "response",
                                "data": {
                                    "content": response.content,
                                    "state": response.state.value,
                                    "iteration": response.iteration,
                                    "tool_calls": response.tool_calls or [],
                                    "tool_results": [
                                        {
                                            "name": tr.get("name", ""),
                                            "success": tr.get("success", False),
                                            "output": tr.get("output", "")[:500],
                                        }
                                        for tr in (response.tool_results or [])
                                    ],
                                },
                            }
                        )

                        if response.state.value == "completed":
                            await websocket.send_json(
                                {
                                    "type": "complete",
                                    "data": {
                                        "iterations": response.iteration,
                                        "duration_ms": response.duration_ms,
                                    },
                                }
                            )
                except Exception as e:
                    await websocket.send_json({"type": "error", "error": str(e)})

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif data.get("type") == "cancel":
                await websocket.send_json({"type": "cancelled"})
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass
    finally:
        active_connections.pop(session_id, None)


# Run with: uvicorn src.api.main:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
