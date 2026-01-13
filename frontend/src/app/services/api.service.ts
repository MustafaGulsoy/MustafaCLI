/**
 * API Service - REST Endpoint Integration
 */

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { SessionInfo, HealthResponse, ChatResponse } from '../models/models';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private apiUrl = environment.apiUrl || 'http://localhost:8000';

  constructor(private http: HttpClient) {}

  /**
   * Health check
   */
  getHealth(): Observable<HealthResponse> {
    return this.http.get<HealthResponse>(`${this.apiUrl}/health`);
  }

  /**
   * Create new session
   */
  createSession(workingDir: string = '.', enableRag: boolean = false): Observable<SessionInfo> {
    return this.http.post<SessionInfo>(`${this.apiUrl}/api/sessions`, {
      working_dir: workingDir,
      enable_rag: enableRag
    });
  }

  /**
   * List all sessions
   */
  listSessions(): Observable<SessionInfo[]> {
    return this.http.get<SessionInfo[]>(`${this.apiUrl}/api/sessions`);
  }

  /**
   * Get session info
   */
  getSession(sessionId: string): Observable<SessionInfo> {
    return this.http.get<SessionInfo>(`${this.apiUrl}/api/sessions/${sessionId}`);
  }

  /**
   * Delete session
   */
  deleteSession(sessionId: string): Observable<any> {
    return this.http.delete(`${this.apiUrl}/api/sessions/${sessionId}`);
  }

  /**
   * Send message (non-streaming)
   */
  sendMessage(sessionId: string, message: string): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(`${this.apiUrl}/api/chat`, {
      session_id: sessionId,
      message: message
    });
  }
}
