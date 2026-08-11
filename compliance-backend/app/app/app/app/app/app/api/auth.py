"""
Authentication API routes.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_user,
)
from app.models import User
from app.schemas import (
    LoginRequest, TokenResponse, RefreshRequest,
    UserCreate, UserResponse,
)

import uuid

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email já cadastrado")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return JWT tokens."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
        )

    token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh an expired access token."""
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token type inválido")

    user_id = payload.get("sub")
    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Token inválido")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user
