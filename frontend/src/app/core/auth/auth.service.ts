/**
 * Authentication Service
 * Handles JWT token storage, login, register, refresh, and logout.
 */

import { Injectable, inject, OnDestroy } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap, Subscription, timer } from 'rxjs';
import { environment } from '../../../environments/environment';

interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface RegisterResponse {
  id: string;
  username: string;
  email: string;
}

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

@Injectable({
  providedIn: 'root'
})
export class AuthService implements OnDestroy {
  private http = inject(HttpClient);
  private router = inject(Router);
  private apiUrl = environment.apiUrl;
  private refreshSub: Subscription | null = null;

  constructor() {
    if (this.isAuthenticated) {
      this.scheduleTokenRefresh();
    }
  }

  ngOnDestroy(): void {
    this.clearRefreshTimer();
  }

  /**
   * Login with username and password.
   */
  login(username: string, password: string): Observable<AuthTokens> {
    return this.http.post<AuthTokens>(`${this.apiUrl}/api/v1/auth/login`, {
      username,
      password
    }).pipe(
      tap(tokens => this.storeTokens(tokens))
    );
  }

  /**
   * Register a new user.
   */
  register(username: string, email: string, password: string): Observable<RegisterResponse> {
    return this.http.post<RegisterResponse>(`${this.apiUrl}/api/v1/auth/register`, {
      username,
      email,
      password
    });
  }

  /**
   * Refresh the access token using the stored refresh token.
   */
  refresh(): Observable<AuthTokens> {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    return this.http.post<AuthTokens>(`${this.apiUrl}/api/v1/auth/refresh`, {
      refresh_token: refreshToken
    }).pipe(
      tap(tokens => this.storeTokens(tokens))
    );
  }

  /**
   * Logout: clear tokens and navigate to login.
   */
  logout(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    this.clearRefreshTimer();
    this.router.navigate(['/login']);
  }

  /**
   * Whether the user holds a non-expired access token.
   */
  get isAuthenticated(): boolean {
    const token = this.getToken();
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return payload.exp * 1000 > Date.now();
    } catch {
      return false;
    }
  }

  /**
   * Return the current access token (or null).
   */
  getToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  // ---- private helpers ----

  private storeTokens(tokens: AuthTokens): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
    this.scheduleTokenRefresh();
  }

  /**
   * Schedule a refresh 60 seconds before the access token expires.
   */
  private scheduleTokenRefresh(): void {
    this.clearRefreshTimer();
    const token = this.getToken();
    if (!token) return;

    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const expiresAt = payload.exp * 1000;
      const refreshIn = expiresAt - Date.now() - 60_000; // 60s before expiry

      if (refreshIn <= 0) {
        // Token is already (nearly) expired – try refreshing now
        this.refresh().subscribe({
          error: () => this.logout()
        });
        return;
      }

      this.refreshSub = timer(refreshIn).subscribe(() => {
        this.refresh().subscribe({
          error: () => this.logout()
        });
      });
    } catch {
      // Malformed token – do nothing
    }
  }

  private clearRefreshTimer(): void {
    if (this.refreshSub) {
      this.refreshSub.unsubscribe();
      this.refreshSub = null;
    }
  }
}
