/**
 * WebSocket Service - Real-time Streaming with Reconnect
 */

import { Injectable, OnDestroy } from '@angular/core';
import { Observable, Subject, BehaviorSubject, Observer, Subscription, timer } from 'rxjs';
import { WebSocketMessage } from '../models/models';
import { environment } from '../../environments/environment';

export type ConnectionState = 'connected' | 'disconnected' | 'reconnecting';

@Injectable({
  providedIn: 'root'
})
export class WebSocketService implements OnDestroy {
  private wsUrl = environment.wsUrl || 'ws://localhost:8000';
  private socket?: WebSocket;
  private messagesSubject = new Subject<WebSocketMessage>();
  private connectionStateSubject = new BehaviorSubject<ConnectionState>('disconnected');

  private currentSessionId?: string;
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 10;
  private readonly maxBackoffMs = 30000;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private heartbeatSubscription?: Subscription;
  private intentionalClose = false;

  public messages$ = this.messagesSubject.asObservable();
  public connectionState$ = this.connectionStateSubject.asObservable();

  get isConnected(): boolean {
    return this.connectionStateSubject.value === 'connected';
  }

  /**
   * Connect to WebSocket with auto-reconnect support
   */
  connect(sessionId: string): Observable<boolean> {
    this.currentSessionId = sessionId;
    this.intentionalClose = false;
    this.reconnectAttempts = 0;

    return this._connect(sessionId);
  }

  private _connect(sessionId: string): Observable<boolean> {
    return new Observable((observer: Observer<boolean>) => {
      const url = `${this.wsUrl}/ws/${sessionId}`;
      console.log('Connecting to WebSocket:', url);

      // Clean up previous socket if any
      this.cleanupSocket();

      try {
        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
          console.log('WebSocket connected');
          this.connectionStateSubject.next('connected');
          this.reconnectAttempts = 0;
          this.startHeartbeat();
          observer.next(true);
          observer.complete();
        };

        this.socket.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            this.messagesSubject.next(message);
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

        this.socket.onerror = (error) => {
          console.error('WebSocket error:', error);
          observer.error(error);
        };

        this.socket.onclose = () => {
          console.log('WebSocket closed');
          this.stopHeartbeat();
          this.connectionStateSubject.next('disconnected');

          if (!this.intentionalClose) {
            this.scheduleReconnect();
          }
        };

      } catch (error) {
        console.error('Error creating WebSocket:', error);
        observer.error(error);
      }
    });
  }

  /**
   * Schedule a reconnect with exponential backoff
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error(`Max reconnect attempts (${this.maxReconnectAttempts}) reached. Giving up.`);
      this.connectionStateSubject.next('disconnected');
      return;
    }

    if (!this.currentSessionId) {
      return;
    }

    this.connectionStateSubject.next('reconnecting');
    this.reconnectAttempts++;

    const backoffMs = Math.min(
      Math.pow(2, this.reconnectAttempts - 1) * 1000,
      this.maxBackoffMs
    );

    console.log(
      `Reconnecting in ${backoffMs}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    );

    this.reconnectTimer = setTimeout(() => {
      if (this.currentSessionId && !this.intentionalClose) {
        this._connect(this.currentSessionId).subscribe({
          next: () => console.log('Reconnected successfully'),
          error: (err) => console.error('Reconnect failed:', err)
        });
      }
    }, backoffMs);
  }

  /**
   * Start heartbeat ping every 30 seconds
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatSubscription = timer(30000, 30000).subscribe(() => {
      this.ping();
    });
  }

  /**
   * Stop heartbeat
   */
  private stopHeartbeat(): void {
    if (this.heartbeatSubscription) {
      this.heartbeatSubscription.unsubscribe();
      this.heartbeatSubscription = undefined;
    }
  }

  /**
   * Clean up existing socket without triggering reconnect
   */
  private cleanupSocket(): void {
    if (this.socket) {
      // Remove handlers to prevent triggering reconnect
      this.socket.onopen = null;
      this.socket.onmessage = null;
      this.socket.onerror = null;
      this.socket.onclose = null;
      if (this.socket.readyState === WebSocket.OPEN ||
          this.socket.readyState === WebSocket.CONNECTING) {
        this.socket.close();
      }
      this.socket = undefined;
    }
  }

  /**
   * Send message to agent
   */
  sendMessage(content: string): void {
    if (!this.socket || !this.isConnected) {
      console.error('WebSocket not connected');
      return;
    }

    const message = {
      type: 'message',
      content: content
    };

    this.socket.send(JSON.stringify(message));
  }

  /**
   * Send ping (keep-alive)
   */
  ping(): void {
    if (!this.socket || !this.isConnected) {
      return;
    }

    this.socket.send(JSON.stringify({ type: 'ping' }));
  }

  /**
   * Cancel current operation
   */
  cancel(): void {
    if (!this.socket || !this.isConnected) {
      return;
    }

    this.socket.send(JSON.stringify({ type: 'cancel' }));
  }

  /**
   * Disconnect WebSocket (intentional)
   */
  disconnect(): void {
    this.intentionalClose = true;
    this.currentSessionId = undefined;
    this.reconnectAttempts = 0;
    this.stopHeartbeat();

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }

    this.cleanupSocket();
    this.connectionStateSubject.next('disconnected');
  }

  ngOnDestroy(): void {
    this.disconnect();
    this.messagesSubject.complete();
    this.connectionStateSubject.complete();
  }
}
