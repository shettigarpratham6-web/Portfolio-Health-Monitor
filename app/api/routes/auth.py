"""
Portfolio Health Monitor
Authentication & User Identity API Endpoints
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.database.connection import get_db
from app.models.user import User
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.schemas.portfolio import ErrorResponse

logger = logging.getLogger("agentx.api.auth")
settings = get_settings()

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    summary="Register New User",
    description="Registers a new user account with unique email address and hashed password.",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    responses={
        201: {"description": "User successfully registered."},
        400: {"model": ErrorResponse, "description": "Invalid registration parameters."},
        409: {"model": ErrorResponse, "description": "Email address already registered."},
    },
)
async def register_user(
    payload: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Creates a new user record after ensuring email uniqueness."""
    clean_email = payload.email.strip().lower()

    # Check for existing account with this email
    stmt = select(User).where(User.email == clean_email)
    existing_user = await db.scalar(stmt)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{clean_email}' already exists.",
        )

    user = User(
        email=clean_email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name.strip() if payload.full_name else None,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("Registered new user | id=%s | email=%s", user.id, user.email)
    return UserResponse.model_validate(user)


@router.post(
    "/token",
    summary="OAuth2 Password Login (Form Data)",
    description="Authenticates credentials via standard OAuth2 password flow for Swagger UI and CLI tools.",
    response_model=TokenResponse,
    responses={
        200: {"description": "Authentication successful; returns signed JWT Bearer token."},
        401: {"model": ErrorResponse, "description": "Incorrect email or password."},
        403: {"model": ErrorResponse, "description": "Account is deactivated."},
    },
)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticates username (email) & password, returning a signed JWT access token."""
    email = form_data.username.strip().lower()
    stmt = select(User).where(User.email == email)
    user = await db.scalar(stmt)

    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning("Failed login attempt for email: %s", email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    access_token = create_access_token(subject=user.id)
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    logger.info("User authenticated via form token | user_id=%s", user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in_seconds,
    )


@router.post(
    "/login",
    summary="JSON Login",
    description="Authenticates credentials via JSON body payload, returning a signed JWT Bearer token.",
    response_model=TokenResponse,
    responses={
        200: {"description": "Authentication successful; returns signed JWT Bearer token."},
        401: {"model": ErrorResponse, "description": "Incorrect email or password."},
        403: {"model": ErrorResponse, "description": "Account is deactivated."},
    },
)
async def login_json(
    payload: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticates email & password via JSON, returning signed JWT access token."""
    email = payload.email.strip().lower()
    stmt = select(User).where(User.email == email)
    user = await db.scalar(stmt)

    if not user or not verify_password(payload.password, user.hashed_password):
        logger.warning("Failed JSON login attempt for email: %s", email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    access_token = create_access_token(subject=user.id)
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    logger.info("User authenticated via JSON login | user_id=%s", user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in_seconds,
    )


@router.get(
    "/me",
    summary="Current User Profile",
    description="Returns public profile details for the currently authenticated user.",
    response_model=UserResponse,
    responses={
        200: {"description": "Authenticated user profile."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
    },
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Returns authenticated user profile details."""
    return UserResponse.model_validate(current_user)

