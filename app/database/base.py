"""
Portfolio Health Monitor
Database Declarative Base & Metadata Configuration for SQLAlchemy 2.0 & Alembic
"""

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from sqlalchemy import MetaData, DateTime, String, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ------------------------------------------------------------------------------
# PostgreSQL Naming Conventions for Predictable Constraint Names
# ------------------------------------------------------------------------------
# Critical for Alembic migrations to generate, alter, and drop constraints
# cleanly across PostgreSQL without collision or database-generated anonymous names.
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy 2.0 declarative models in Portfolio Health Monitor.
    All future domain models inherit from this base.
    """
    metadata = MetaData(naming_convention=POSTGRES_NAMING_CONVENTION)

    def __repr__(self) -> str:
        """Informative string representation for debugging."""
        attrs = ", ".join(
            f"{key}={value!r}"
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        )
        return f"{self.__class__.__name__}({attrs})"


class TimestampMixin:
    """
    Reusable declarative mixin providing UTC timestamp auditing.
    Subclasses will automatically receive created_at and updated_at columns.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


def compute_short_id(prefix: str, uid: Any) -> str:
    """Deterministically generate a compact ID (e.g., usr_8f82b13f) from a UUID."""
    if isinstance(uid, uuid.UUID):
        hex_str = uid.hex
    elif isinstance(uid, str):
        hex_str = uid.replace("-", "")
    else:
        hex_str = uuid.uuid4().hex
    return f"{prefix}_{hex_str[:8]}"


class ShortIdMixin:
    """
    Reusable mixin providing human-readable compact short_id (e.g. usr_8f82b13f).
    Automatically derived from primary key UUID for compact table displays and logs.
    """
    __short_id_prefix__: str = "obj"

    short_id: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        default=lambda: f"obj_{uuid.uuid4().hex[:8]}",
    )


@event.listens_for(Base, "before_insert", propagate=True)
def _before_insert_short_id(mapper: Any, connection: Any, target: Any) -> None:
    prefix = getattr(target, "__short_id_prefix__", None)
    if prefix is not None:
        uid = getattr(target, "id", None)
        target.short_id = compute_short_id(prefix, uid)



