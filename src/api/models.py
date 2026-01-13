"""
API Models - Pydantic Schemas
==============================

Data models for API requests and responses.

Author: Mustafa (Kardelen Yazılım)
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """Message role"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatRequest(BaseModel):
    """Chat request"""
    session_id: str = Field(..., description="Session ID")
    message: str = Field(..., description="User message")


class ToolCall(BaseModel):
    """Tool call information"""
    name: str
    arguments: Dict[str, Any]


class ToolResult(BaseModel):
    """Tool execution result"""
    name: str
    success: bool
    output: str


class ChatResponse(BaseModel):
    """Chat response"""
    content: str = Field(..., description="Response content")
    state: str = Field(..., description="Agent state")
    iteration: int = Field(..., description="Current iteration")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)


class SessionInfo(BaseModel):
    """Session information"""
    session_id: str
    created_at: datetime
    working_dir: str
    rag_enabled: bool
    active: bool


class HealthResponse(BaseModel):
    """Health check response"""
    status: str  # healthy, degraded, unhealthy
    ollama_connected: bool
    rag_available: bool
    active_sessions: int
    timestamp: datetime


class AgentStatus(BaseModel):
    """Agent status"""
    state: str
    current_iteration: int
    max_iterations: int


class FileInfo(BaseModel):
    """File information"""
    path: str
    name: str
    size: int
    modified: datetime
    is_directory: bool


class CodeSnippet(BaseModel):
    """Code snippet"""
    file_path: str
    line_start: int
    line_end: int
    content: str
    language: str = "python"


class RAGSearchRequest(BaseModel):
    """RAG search request"""
    query: str = Field(..., description="Search query")
    n_results: int = Field(5, description="Number of results")
    min_score: float = Field(0.5, description="Minimum relevance score")


class RAGSearchResult(BaseModel):
    """RAG search result"""
    file_path: str
    name: str
    chunk_type: str
    line_start: int
    line_end: int
    content: str
    score: float
    docstring: Optional[str] = None
