/**
 * Login / Register Component
 * Standalone component with toggle between login and register forms.
 */

import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.component.html',
  styles: [`
    .auth-wrapper {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      background: #0f0f0f;
    }
    .auth-card {
      background: #1a1a2e;
      border: 1px solid #333;
      border-radius: 12px;
      padding: 2rem;
      width: 100%;
      max-width: 400px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    }
    .auth-card h2 {
      color: #e0e0e0;
      text-align: center;
      margin-bottom: 1.5rem;
    }
    .form-group {
      margin-bottom: 1rem;
    }
    .form-group label {
      display: block;
      color: #aaa;
      margin-bottom: 0.3rem;
      font-size: 0.9rem;
    }
    .form-group input {
      width: 100%;
      padding: 0.6rem 0.8rem;
      border: 1px solid #444;
      border-radius: 6px;
      background: #16213e;
      color: #e0e0e0;
      font-size: 1rem;
      box-sizing: border-box;
    }
    .form-group input:focus {
      outline: none;
      border-color: #6c63ff;
    }
    .btn-submit {
      width: 100%;
      padding: 0.7rem;
      border: none;
      border-radius: 6px;
      background: #6c63ff;
      color: #fff;
      font-size: 1rem;
      cursor: pointer;
      margin-top: 0.5rem;
    }
    .btn-submit:hover {
      background: #5a52d5;
    }
    .btn-submit:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .toggle-link {
      text-align: center;
      margin-top: 1rem;
      color: #aaa;
      font-size: 0.9rem;
    }
    .toggle-link a {
      color: #6c63ff;
      cursor: pointer;
      text-decoration: none;
    }
    .toggle-link a:hover {
      text-decoration: underline;
    }
    .error-msg {
      color: #ff6b6b;
      background: rgba(255, 107, 107, 0.1);
      border: 1px solid rgba(255, 107, 107, 0.3);
      border-radius: 6px;
      padding: 0.5rem 0.8rem;
      margin-bottom: 1rem;
      font-size: 0.9rem;
      text-align: center;
    }
  `]
})
export class LoginComponent {
  private authService = inject(AuthService);
  private router = inject(Router);

  isRegisterMode = false;
  username = '';
  email = '';
  password = '';
  error = '';
  loading = false;

  toggleMode(): void {
    this.isRegisterMode = !this.isRegisterMode;
    this.error = '';
  }

  onSubmit(): void {
    this.error = '';
    this.loading = true;

    if (this.isRegisterMode) {
      this.authService.register(this.username, this.email, this.password).subscribe({
        next: () => {
          // After successful registration, log in automatically
          this.authService.login(this.username, this.password).subscribe({
            next: () => {
              this.loading = false;
              this.router.navigate(['/']);
            },
            error: (err) => {
              this.loading = false;
              this.error = err.error?.detail || 'Login after registration failed. Please log in manually.';
              this.isRegisterMode = false;
            }
          });
        },
        error: (err) => {
          this.loading = false;
          this.error = err.error?.detail || 'Registration failed. Please try again.';
        }
      });
    } else {
      this.authService.login(this.username, this.password).subscribe({
        next: () => {
          this.loading = false;
          this.router.navigate(['/']);
        },
        error: (err) => {
          this.loading = false;
          this.error = err.error?.detail || 'Invalid username or password.';
        }
      });
    }
  }
}
