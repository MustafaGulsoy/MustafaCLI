/**
 * AuthService Unit Tests
 */

import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { AuthService } from './auth.service';
import { environment } from '../../../environments/environment';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;

  const mockTokens = {
    access_token: buildJwt({ sub: 'user1', exp: Math.floor(Date.now() / 1000) + 3600 }),
    refresh_token: 'mock-refresh-token',
    token_type: 'bearer'
  };

  /** Build a minimal JWT with a given payload. */
  function buildJwt(payload: Record<string, unknown>): string {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const body = btoa(JSON.stringify(payload));
    return `${header}.${body}.signature`;
  }

  beforeEach(() => {
    localStorage.clear();

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule, RouterTestingModule]
    });

    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('login', () => {
    it('should store tokens on successful login', () => {
      service.login('user1', 'pass123').subscribe();

      const req = httpMock.expectOne(`${environment.apiUrl}/api/v1/auth/login`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({ username: 'user1', password: 'pass123' });

      req.flush(mockTokens);

      expect(localStorage.getItem('access_token')).toBe(mockTokens.access_token);
      expect(localStorage.getItem('refresh_token')).toBe(mockTokens.refresh_token);
    });
  });

  describe('logout', () => {
    it('should clear tokens from localStorage', () => {
      localStorage.setItem('access_token', 'some-token');
      localStorage.setItem('refresh_token', 'some-refresh');

      service.logout();

      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
    });
  });

  describe('isAuthenticated', () => {
    it('should return false when no token is stored', () => {
      expect(service.isAuthenticated).toBeFalse();
    });

    it('should return true when a valid non-expired token is stored', () => {
      localStorage.setItem('access_token', mockTokens.access_token);
      expect(service.isAuthenticated).toBeTrue();
    });

    it('should return false when the token is expired', () => {
      const expiredToken = buildJwt({ sub: 'user1', exp: Math.floor(Date.now() / 1000) - 100 });
      localStorage.setItem('access_token', expiredToken);
      expect(service.isAuthenticated).toBeFalse();
    });
  });

  describe('getToken', () => {
    it('should return null when no token is stored', () => {
      expect(service.getToken()).toBeNull();
    });

    it('should return the stored access token', () => {
      localStorage.setItem('access_token', 'my-access-token');
      expect(service.getToken()).toBe('my-access-token');
    });
  });
});
