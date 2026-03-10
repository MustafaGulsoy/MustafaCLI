"""Tests for JWT authentication system."""
from __future__ import annotations

import pytest

from src.auth.password import hash_password, verify_password
from src.auth.jwt_handler import create_access_token, create_refresh_token, decode_token


class TestPasswordHashing:
    def test_hash_password(self):
        hashed = hash_password("secret123")
        assert hashed != "secret123"
        assert len(hashed) > 20

    def test_verify_correct_password(self):
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed)

    def test_verify_wrong_password(self):
        hashed = hash_password("secret123")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_same_password(self):
        h1 = hash_password("secret123")
        h2 = hash_password("secret123")
        assert h1 != h2  # bcrypt uses random salt


class TestJWTHandler:
    def test_create_access_token(self):
        token = create_access_token({"sub": "testuser", "user_id": 1})
        assert isinstance(token, str)
        assert len(token) > 10

    def test_decode_access_token(self):
        token = create_access_token({"sub": "testuser", "user_id": 1})
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["user_id"] == 1
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        token = create_refresh_token({"sub": "testuser", "user_id": 1})
        payload = decode_token(token)
        assert payload is not None
        assert payload["type"] == "refresh"

    def test_expired_token(self):
        token = create_access_token({"sub": "test"}, expires_minutes=-1)
        payload = decode_token(token)
        assert payload is None

    def test_invalid_token(self):
        payload = decode_token("invalid.token.here")
        assert payload is None

    def test_token_contains_user_data(self):
        data = {"sub": "admin", "user_id": 42, "role": "admin"}
        token = create_access_token(data)
        payload = decode_token(token)
        assert payload["sub"] == "admin"
        assert payload["user_id"] == 42
        assert payload["role"] == "admin"
