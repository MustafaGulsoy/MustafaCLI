"""Authentication API routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from ..db.database import get_session
from ..db.models import User
from .jwt_handler import create_access_token, create_refresh_token, decode_token
from .password import hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest) -> TokenResponse:
    """Register a new user."""
    async with get_session() as session:
        # Check existing username
        result = await session.execute(
            select(User).where(User.username == req.username)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        # Check existing email
        result = await session.execute(
            select(User).where(User.email == req.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )

        user = User(
            username=req.username,
            email=req.email,
            hashed_password=hash_password(req.password),
        )
        session.add(user)
        await session.flush()
        return _create_tokens(user)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    """Login and get tokens."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.username == req.username)
        )
        user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return _create_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest) -> TokenResponse:
    """Refresh access token."""
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.id == payload.get("user_id"))
        )
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return _create_tokens(user)


def _create_tokens(user: User) -> TokenResponse:
    """Generate access and refresh tokens for a user."""
    data = {"sub": user.username, "user_id": user.id}
    return TokenResponse(
        access_token=create_access_token(data),
        refresh_token=create_refresh_token(data),
    )
