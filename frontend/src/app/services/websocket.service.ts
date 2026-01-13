/**
 * WebSocket Service - Real-time Streaming
 */

import { Injectable } from '@angular/core';
import { Observable, Subject, Observer } from 'rxjs';
import { WebSocketMessage } from '../models/models';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class WebSocketService {
  private wsUrl = environment.wsUrl || 'ws://localhost:8000';
  private socket?: WebSocket;
  private messagesSubject = new Subject<WebSocketMessage>();

  public messages$ = this.messagesSubject.asObservable();
  public isConnected = false;

  /**
   * Connect to WebSocket
   */
  connect(sessionId: string): Observable<boolean> {
    return new Observable((observer: Observer<boolean>) => {
      const url = `${this.wsUrl}/ws/${sessionId}`;
      console.log('Connecting to WebSocket:', url);

      try {
        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
          console.log('WebSocket connected');
          this.isConnected = true;
          observer.next(true);
          observer.complete();
        };

        this.socket.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            console.log('WebSocket message:', message);
            this.messagesSubject.next(message);
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

        this.socket.onerror = (error) => {
          console.error('WebSocket error:', error);
          this.isConnected = false;
          observer.error(error);
        };

        this.socket.onclose = () => {
          console.log('WebSocket closed');
          this.isConnected = false;
          this.messagesSubject.complete();
        };

      } catch (error) {
        console.error('Error creating WebSocket:', error);
        observer.error(error);
      }
    });
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
   * Disconnect WebSocket
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.close();
      this.socket = undefined;
      this.isConnected = false;
    }
  }
}
