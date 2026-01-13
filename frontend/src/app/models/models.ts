/**
 * TypeScript Models - Frontend Data Types
 * Matches backend Pydantic models
 */

export interface SessionInfo {
  session_id: string;
  created_at: string;
  working_dir: string;
  rag_enabled: boolean;
  active: boolean;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  tool_calls?: ToolCall[];
  tool_results?: ToolResult[];
  iteration?: number;
}

export interface ToolCall {
  name: string;
  arguments: any;
}

export interface ToolResult {
  name: string;
  success: boolean;
  output: string;
}

export interface ChatResponse {
  content: string;
  state: string;
  iteration: number;
  tool_calls: any[];
  tool_results: any[];
}

export interface WebSocketMessage {
  type: 'connected' | 'response' | 'complete' | 'error' | 'pong';
  session_id?: string;
  working_dir?: string;
  rag_enabled?: boolean;
  data?: any;
  error?: string;
}

export interface HealthResponse {
  status: string;
  ollama_connected: boolean;
  rag_available: boolean;
  active_sessions: number;
  timestamp: string;
}
