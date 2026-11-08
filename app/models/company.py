"""
AgentX – Portfolio Health Monitor
Company Model
"""

from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import Boolean, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.holding import Holding
    from app.models.monitoring_alert import MonitoringAlert
    from app.models.research_event import ResearchEvent


class Company(Base, TimestampMixin):
    """
    Company entity representing a publicly traded asset or equity.
    Tracked across portfolios and monitored by intelligence agents.
    """
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ticker: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    sector: Mapped[Optional[str]] = mapped_column(
        String(100),
        index=True,
        nullable=True,
    )
    industry: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    exchange: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    country: Mapped[str] = mapped_column(
        String(10),
        default="US",
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    website: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    holdings: Mapped[List["Holding"]] = relationship(
        "Holding",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    research_events: Mapped[List["ResearchEvent"]] = relationship(
        "ResearchEvent",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    alerts: Mapped[List["MonitoringAlert"]] = relationship(
        "MonitoringAlert",
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

