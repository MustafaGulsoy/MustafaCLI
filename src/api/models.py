"""
API Models - Pydantic Schemas
==============================

Data models for API requests and responses.

Author: Mustafa (Kardelen Yazilim)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# --- Auth Models ---


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --- Chat Models ---


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="User message")


class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]


class ToolResult(BaseModel):
    name: str
    success: bool
    output: str


class ChatResponse(BaseModel):
    content: str = Field(..., description="Response content")
    state: str = Field(..., description="Agent state")
    iteration: int = Field(..., description="Current iteration")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)


# --- Session Models ---


class SessionInfo(BaseModel):
    session_id: str
    created_at: datetime
    working_dir: str
    rag_enabled: bool
    active: bool


class SessionCreateRequest(BaseModel):
    working_dir: str = "."
    enable_rag: bool = False
    model_name: str = "qwen2.5-coder:7b"


# --- Health Models ---


class HealthResponse(BaseModel):
    status: str  # healthy, degraded, unhealthy
    ollama_connected: bool
    rag_available: bool
    active_sessions: int
    timestamp: datetime


class AgentStatus(BaseModel):
    state: str
    current_iteration: int
    max_iterations: int


# --- File / Code Models ---


class FileInfo(BaseModel):
    path: str
    name: str
    size: int
    modified: datetime
    is_directory: bool


class CodeSnippet(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    content: str
    language: str = "python"


# --- RAG Models ---


class RAGSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    n_results: int = Field(5, description="Number of results")
    min_score: float = Field(0.5, description="Minimum relevance score")


class RAGSearchResult(BaseModel):
    file_path: str
    name: str
    chunk_type: str
    line_start: int
    line_end: int
    content: str
    score: float
    docstring: Optional[str] = None


# --- Plugin Models ---


class PluginInfo(BaseModel):
    name: str
    version: str
    description: str
    plugin_type: str
    enabled: bool


# --- Error Models ---


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
