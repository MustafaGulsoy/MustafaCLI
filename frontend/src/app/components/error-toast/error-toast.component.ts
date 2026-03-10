/**
 * Error Toast Component - Global Notification System
 * Standalone Angular 17 component
 */

import { Component, Injectable, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subject, Subscription, timer } from 'rxjs';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: number;
  type: ToastType;
  message: string;
  autoDismiss: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ToastService {
  private toastsSubject = new Subject<Toast[]>();
  private toasts: Toast[] = [];
  private nextId = 0;

  toasts$ = this.toastsSubject.asObservable();

  show(message: string, type: ToastType = 'info', autoDismissMs = 5000): void {
    const toast: Toast = {
      id: this.nextId++,
      type,
      message,
      autoDismiss: autoDismissMs > 0
    };

    this.toasts = [...this.toasts, toast];
    this.toastsSubject.next(this.toasts);

    if (autoDismissMs > 0) {
      timer(autoDismissMs).subscribe(() => this.dismiss(toast.id));
    }
  }

  success(message: string): void {
    this.show(message, 'success');
  }

  error(message: string): void {
    this.show(message, 'error');
  }

  warning(message: string): void {
    this.show(message, 'warning');
  }

  info(message: string): void {
    this.show(message, 'info');
  }

  dismiss(id: number): void {
    this.toasts = this.toasts.filter(t => t.id !== id);
    this.toastsSubject.next(this.toasts);
  }

  clear(): void {
    this.toasts = [];
    this.toastsSubject.next(this.toasts);
  }
}

@Component({
  selector: 'app-error-toast',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="toast-container">
      @for (toast of toasts; track toast.id) {
        <div
          class="toast"
          [class]="'toast toast-' + toast.type"
          (click)="dismiss(toast.id)"
        >
          <span class="toast-icon">{{ getIcon(toast.type) }}</span>
          <span class="toast-message">{{ toast.message }}</span>
          <button class="toast-close" (click)="dismiss(toast.id); $event.stopPropagation()">
            &times;
          </button>
        </div>
      }
    </div>
  `,
  styles: [`
    .toast-container {
      position: fixed;
      top: 16px;
      right: 16px;
      z-index: 10000;
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-width: 400px;
    }

    .toast {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 12px 16px;
      border-radius: 8px;
      color: #fff;
      font-size: 14px;
      cursor: pointer;
      animation: slideIn 0.25s ease-out;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }

    .toast-success {
      background: #2e7d32;
    }

    .toast-error {
      background: #c62828;
    }

    .toast-warning {
      background: #e65100;
    }

    .toast-info {
      background: #1565c0;
    }

    .toast-icon {
      font-size: 18px;
      flex-shrink: 0;
    }

    .toast-message {
      flex: 1;
      word-break: break-word;
    }

    .toast-close {
      background: none;
      border: none;
      color: #fff;
      font-size: 20px;
      cursor: pointer;
      padding: 0 0 0 8px;
      opacity: 0.7;
      flex-shrink: 0;
    }

    .toast-close:hover {
      opacity: 1;
    }

    @keyframes slideIn {
      from {
        transform: translateX(100%);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
  `]
})
export class ErrorToastComponent implements OnDestroy {
  toasts: Toast[] = [];
  private subscription: Subscription;

  constructor(private toastService: ToastService) {
    this.subscription = this.toastService.toasts$.subscribe(
      toasts => this.toasts = toasts
    );
  }

  getIcon(type: ToastType): string {
    switch (type) {
      case 'success': return '\u2713';
      case 'error': return '\u2717';
      case 'warning': return '\u26A0';
      case 'info': return '\u2139';
    }
  }

  dismiss(id: number): void {
    this.toastService.dismiss(id);
  }

  ngOnDestroy(): void {
    this.subscription.unsubscribe();
  }
}
