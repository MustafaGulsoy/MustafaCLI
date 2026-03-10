/**
 * Auth Interceptor
 * Attaches Bearer token to API requests and handles 401 responses.
 */

import { inject } from '@angular/core';
import {
  HttpInterceptorFn,
  HttpRequest,
  HttpHandlerFn,
  HttpErrorResponse
} from '@angular/common/http';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn
) => {
  const authService = inject(AuthService);

  // Only attach token to /api/ requests
  const isApiRequest = req.url.includes('/api/');
  // Never attach token to auth endpoints to avoid circular refresh
  const isAuthRequest = req.url.includes('/api/v1/auth/');

  let request = req;
  if (isApiRequest && !isAuthRequest) {
    const token = authService.getToken();
    if (token) {
      request = req.clone({
        setHeaders: { Authorization: `Bearer ${token}` }
      });
    }
  }

  return next(request).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401 && isApiRequest && !isAuthRequest) {
        return authService.refresh().pipe(
          switchMap(tokens => {
            const retryReq = req.clone({
              setHeaders: { Authorization: `Bearer ${tokens.access_token}` }
            });
            return next(retryReq);
          }),
          catchError(() => {
            authService.logout();
            return throwError(() => error);
          })
        );
      }
      return throwError(() => error);
    })
  );
};
