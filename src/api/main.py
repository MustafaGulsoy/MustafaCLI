"""
FastAPI Main Application
=========================

Web API for MustafaCLI with real-time WebSocket streaming.

Features:
- REST API endpoints
- WebSocket for real-time agent streaming
- CORS for Angular frontend
- Session management
- Health checks

Author: Mustafa (Kardelen Yazılım)
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from ..core.agent import Agent, AgentConfig
from ..core.providers import create_provider
from ..core.tools import create_default_tools
from .sessions import SessionManager
from .models import (
    ChatRequest,
    ChatResponse,
    SessionInfo,
    HealthResponse,
    AgentStatus
)

# Create FastAPI app
app = FastAPI(
    title="MustafaCLI API",
    description="AI Coding Agent API with real-time streaming",
    version="0.4.0"
)

# CORS configuration for Angular
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",  # Angular dev server
        "http://localhost:8080",  # Alternative port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session manager
session_manager = SessionManager()

# Active WebSocket connections
active_connections: Dict[str, WebSocket] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    print("🚀 MustafaCLI API starting...")
    print("📡 WebSocket endpoint: ws://localhost:8000/ws/{session_id}")
    print("🌐 REST API: http://localhost:8000/docs")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("👋 MustafaCLI API shutting down...")


@app.get("/", response_model=Dict)
async def root():
    """Root endpoint"""
    return {
        "name": "MustafaCLI API",
        "version": "0.4.0",
        "status": "running",
        "docs": "/docs",
        "websocket": "/ws/{session_id}"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        # Check Ollama
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=2)
            ollama_status = response.status_code == 200
    except:
        ollama_status = False

    # Check RAG
    rag_db_path = Path(".rag_db")
    rag_status = rag_db_path.exists()

    return HealthResponse(
        status="healthy" if ollama_status else "degraded",
        ollama_connected=ollama_status,
        rag_available=rag_status,
        active_sessions=len(session_manager.sessions),
        timestamp=datetime.now()
    )


@app.post("/api/sessions", response_model=SessionInfo)
async def create_session(
    working_dir: str = ".",
    enable_rag: bool = False
):
    """Create new agent session"""
    try:
        session = await session_manager.create_session(
            working_dir=working_dir,
            enable_rag=enable_rag
        )
        return session.to_info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions", response_model=List[SessionInfo])
async def list_sessions():
    """List all active sessions"""
    return [
        session.to_info()
        for session in session_manager.sessions.values()
    ]


@app.get("/api/sessions/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """Get session info"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.to_info()


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete session"""
    success = await session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send message to agent (non-streaming)

    For streaming, use WebSocket endpoint instead.
    """
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        # Run agent (collect all responses)
        responses = []
        async for response in session.agent.run(request.message):
            responses.append(response)

        # Return final response
        final = responses[-1] if responses else None
        if final:
            return ChatResponse(
                content=final.content,
                state=final.state.value,
                iteration=final.iteration,
                tool_calls=final.tool_calls or [],
                tool_results=[
                    {
                        "name": tr.get("name", ""),
                        "success": tr.get("success", False),
                        "output": tr.get("output", "")
                    }
                    for tr in (final.tool_results or [])
                ]
            )
        else:
            raise HTTPException(status_code=500, detail="No response from agent")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time streaming

    Protocol:
    - Client sends: {"type": "message", "content": "..."}
    - Server sends: {"type": "response", "data": {...}}
    - Server sends: {"type": "complete", "data": {...}}
    - Server sends: {"type": "error", "error": "..."}
    """
    await websocket.accept()
    active_connections[session_id] = websocket

    try:
        # Get or create session
        session = session_manager.get_session(session_id)
        if not session:
            await websocket.send_json({
                "type": "error",
                "error": "Session not found. Create session first."
            })
            await websocket.close()
            return

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "working_dir": session.working_dir,
            "rag_enabled": session.rag_enabled
        })

        # Listen for messages
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            if data.get("type") == "message":
                message = data.get("content", "")

                if not message:
                    await websocket.send_json({
                        "type": "error",
                        "error": "Empty message"
                    })
                    continue

                # Run agent and stream responses
                try:
                    async for response in session.agent.run(message):
                        # Send each response chunk
                        await websocket.send_json({
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
                                        "output": tr.get("output", "")[:500]  # Truncate
                                    }
                                    for tr in (response.tool_results or [])
                                ]
                            }
                        })

                        # If completed, send complete message
                        if response.state.value == "completed":
                            await websocket.send_json({
                                "type": "complete",
                                "data": {
                                    "iterations": response.iteration,
                                    "duration_ms": response.duration_ms
                                }
                            })

                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e)
                    })

            elif data.get("type") == "ping":
                # Keep-alive
                await websocket.send_json({"type": "pong"})

            elif data.get("type") == "cancel":
                # Cancel current operation
                await websocket.send_json({
                    "type": "cancelled"
                })
                break

    except WebSocketDisconnect:
        print(f"Client disconnected: {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": str(e)
            })
        except:
            pass
    finally:
        # Cleanup
        if session_id in active_connections:
            del active_connections[session_id]


@app.get("/api/status", response_model=AgentStatus)
async def get_agent_status(session_id: str):
    """Get current agent status"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return AgentStatus(
        state=session.agent.state.value,
        current_iteration=session.agent.current_iteration,
        max_iterations=session.agent.config.max_iterations
    )


# Run with: uvicorn src.api.main:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
