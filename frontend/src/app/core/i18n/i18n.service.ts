import { Injectable, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export type Locale = 'en' | 'tr';

@Injectable({ providedIn: 'root' })
export class I18nService {
  private translations = signal<Record<string, string>>({});
  private currentLocale = signal<Locale>('en');

  locale = computed(() => this.currentLocale());

  constructor(private http: HttpClient) {
    const saved = localStorage.getItem('locale') as Locale;
    if (saved && ['en', 'tr'].includes(saved)) {
      this.setLocale(saved);
    } else {
      this.loadTranslations('en');
    }
  }

  setLocale(locale: Locale): void {
    this.currentLocale.set(locale);
    localStorage.setItem('locale', locale);
    this.loadTranslations(locale);
  }

  t(key: string, params?: Record<string, string | number>): string {
    let value = this.translations()[key] || key;
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        value = value.replace(`{${k}}`, String(v));
      });
    }
    return value;
  }

  private loadTranslations(locale: Locale): void {
    this.http.get<Record<string, string>>(`/assets/i18n/${locale}.json`).subscribe({
      next: (data) => this.translations.set(data),
      error: () => {
        // Fallback to English
        if (locale !== 'en') {
          this.loadTranslations('en');
        }
      }
    });
  }
}
