/**
 * Chat Component - Main Chat Interface
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { ApiService } from '../../services/api.service';
import { WebSocketService } from '../../services/websocket.service';
import { ChatMessage, SessionInfo, WebSocketMessage } from '../../models/models';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.css']
})
export class ChatComponent implements OnInit, OnDestroy {
  messages: ChatMessage[] = [];
  userInput: string = '';
  isLoading: boolean = false;
  isConnected: boolean = false;
  currentSession?: SessionInfo;
  ragEnabled: boolean = true;

  private wsSubscription?: Subscription;

  constructor(
    private apiService: ApiService,
    private wsService: WebSocketService
  ) {}

  ngOnInit(): void {
    this.initializeSession();
  }

  ngOnDestroy(): void {
    this.wsSubscription?.unsubscribe();
    this.wsService.disconnect();
  }

  /**
   * Initialize session
   */
  async initializeSession(): Promise<void> {
    try {
      // Create session
      this.currentSession = await this.apiService.createSession('.', this.ragEnabled).toPromise();
      console.log('Session created:', this.currentSession);

      // Connect WebSocket
      await this.wsService.connect(this.currentSession!.session_id).toPromise();

      // Subscribe to messages
      this.wsSubscription = this.wsService.messages$.subscribe(
        (message: WebSocketMessage) => this.handleWebSocketMessage(message)
      );

      this.isConnected = true;

      // Add welcome message
      this.addMessage({
        role: 'system',
        content: `Connected to MustafaCLI Agent\nRAG: ${this.ragEnabled ? 'Enabled' : 'Disabled'}\nWorking Directory: ${this.currentSession?.working_dir}`,
        timestamp: new Date()
      });

    } catch (error) {
      console.error('Error initializing session:', error);
      this.addMessage({
        role: 'system',
        content: 'Error connecting to agent. Please check if backend is running.',
        timestamp: new Date()
      });
    }
  }

  /**
   * Handle WebSocket messages
   */
  private handleWebSocketMessage(message: WebSocketMessage): void {
    switch (message.type) {
      case 'connected':
        console.log('WebSocket connected:', message);
        break;

      case 'response':
        if (message.data) {
          // Update or add assistant message
          const lastMsg = this.messages[this.messages.length - 1];

          if (lastMsg && lastMsg.role === 'assistant' && lastMsg.iteration === message.data.iteration) {
            // Update existing message
            lastMsg.content = message.data.content;
            lastMsg.tool_calls = message.data.tool_calls;
            lastMsg.tool_results = message.data.tool_results;
          } else {
            // Add new message
            this.addMessage({
              role: 'assistant',
              content: message.data.content,
              timestamp: new Date(),
              tool_calls: message.data.tool_calls,
              tool_results: message.data.tool_results,
              iteration: message.data.iteration
            });
          }
        }
        break;

      case 'complete':
        console.log('Task complete:', message.data);
        this.isLoading = false;
        break;

      case 'error':
        console.error('Error from server:', message.error);
        this.addMessage({
          role: 'system',
          content: `Error: ${message.error}`,
          timestamp: new Date()
        });
        this.isLoading = false;
        break;
    }
  }

  /**
   * Send message
   */
  sendMessage(): void {
    if (!this.userInput.trim() || !this.isConnected || this.isLoading) {
      return;
    }

    // Add user message
    this.addMessage({
      role: 'user',
      content: this.userInput,
      timestamp: new Date()
    });

    // Send via WebSocket
    this.wsService.sendMessage(this.userInput);

    // Clear input and set loading
    this.userInput = '';
    this.isLoading = true;
  }

  /**
   * Add message to chat
   */
  private addMessage(message: ChatMessage): void {
    this.messages.push(message);

    // Scroll to bottom
    setTimeout(() => {
      const chatContainer = document.querySelector('.chat-messages');
      if (chatContainer) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
      }
    }, 100);
  }

  /**
   * Cancel current operation
   */
  cancelOperation(): void {
    this.wsService.cancel();
    this.isLoading = false;
  }

  /**
   * Clear chat
   */
  clearChat(): void {
    this.messages = [];
  }

  /**
   * Toggle RAG
   */
  async toggleRag(): Promise<void> {
    this.ragEnabled = !this.ragEnabled;

    // Reinitialize session
    this.wsService.disconnect();
    this.messages = [];
    await this.initializeSession();
  }
}
