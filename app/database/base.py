"""
AgentX – Portfolio Health Monitor
Database Declarative Base & Metadata Configuration for SQLAlchemy 2.0 & Alembic
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import MetaData, DateTime
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
    Base class for all SQLAlchemy 2.0 declarative models in AgentX.
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

