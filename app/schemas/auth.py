"""
Portfolio Health Monitor
Pydantic Schemas for Authentication & User Identity
"""

from datetime import datetime
import re
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class UserRegisterRequest(BaseModel):
    """Payload for registering a new user account."""
    email: str = Field(
        ...,
        description="Unique user email address",
        examples=["investor@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="User password (8 to 72 characters)",
        examples=["StrongP@ssw0rd!"],
    )
    full_name: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Optional full name or display name",
        examples=["Jane Doe"],
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean or not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email address format.")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise ValueError("Password must contain at least 8 characters.")
        return v


class UserLoginRequest(BaseModel):
    """Payload for JSON-based user login."""
    email: str = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    """Standardized JWT Bearer token response."""
    access_token: str = Field(description="Cryptographically signed JWT access token")
    token_type: str = Field(default="bearer", description="Token authorization type")
    expires_in: int = Field(description="Token validity period in seconds")


class UserResponse(BaseModel):
    """Public user profile response."""
    id: uuid.UUID
    short_id: Optional[str] = None
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

