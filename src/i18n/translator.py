"""Simple i18n translation system."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).parent / "locales"
_cache: dict[str, dict[str, str]] = {}


class Translator:
    def __init__(self, locale: str = "en"):
        self.locale = locale
        self._translations = self._load(locale)
        if locale != "en":
            self._fallback = self._load("en")
        else:
            self._fallback = {}

    def _load(self, locale: str) -> dict[str, str]:
        if locale in _cache:
            return _cache[locale]
        path = _LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            return self._load("en") if locale != "en" else {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache[locale] = data
        return data

    def t(self, key: str, **kwargs: Any) -> str:
        value = self._translations.get(key) or self._fallback.get(key) or key
        if kwargs:
            try:
                value = value.format(**kwargs)
            except (KeyError, IndexError):
                pass
        return value

    def get_locale(self) -> str:
        return self.locale

    def set_locale(self, locale: str) -> None:
        self.locale = locale
        self._translations = self._load(locale)
        if locale != "en":
            self._fallback = self._load("en")
        else:
            self._fallback = {}
