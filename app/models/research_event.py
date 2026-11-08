"""
AgentX – Portfolio Health Monitor
Research Event Model
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.evidence_source import EvidenceSource
    from app.models.monitoring_alert import MonitoringAlert


class ResearchEventType(str, Enum):
    """Categorization of financial and market events."""
    EARNINGS = "EARNINGS"
    REGULATORY = "REGULATORY"
    LEADERSHIP = "LEADERSHIP"
    PRODUCT = "PRODUCT"
    MACRO = "MACRO"
    LITIGATION = "LITIGATION"
    FINANCIAL_DISCLOSURE = "FINANCIAL_DISCLOSURE"
    ANALYST_RATING = "ANALYST_RATING"
    OTHER = "OTHER"


class EventSeverity(str, Enum):
    """Potential impact severity level."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventSentiment(str, Enum):
    """Market sentiment classification."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(str, Enum):
    """Evidence verification status determined by Verification Agent."""
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ResearchEvent(Base, TimestampMixin):
    """
    Evidence-based financial research event discovered by intelligence agents.
    Deduplicated via unique event_hash to guarantee idempotency.
    """
    __tablename__ = "research_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Deduplication hash: SHA-256 of normalized company_id + event_type + canonical content
    event_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    event_type: Mapped[ResearchEventType] = mapped_column(
        SQLEnum(ResearchEventType, native_enum=False, length=50),
        default=ResearchEventType.OTHER,
        nullable=False,
        index=True,
    )
    severity: Mapped[EventSeverity] = mapped_column(
        SQLEnum(EventSeverity, native_enum=False, length=20),
        default=EventSeverity.MEDIUM,
        nullable=False,
    )
    sentiment: Mapped[EventSentiment] = mapped_column(
        SQLEnum(EventSentiment, native_enum=False, length=20),
        default=EventSentiment.NEUTRAL,
        nullable=False,
    )
    impact_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=True,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SQLEnum(VerificationStatus, native_enum=False, length=30),
        default=VerificationStatus.UNVERIFIED,
        nullable=False,
        index=True,
    )
    published_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # Relationships
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="research_events",
    )
    evidence_sources: Mapped[List["EvidenceSource"]] = relationship(
        "EvidenceSource",
        back_populates="research_event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    alerts: Mapped[List["MonitoringAlert"]] = relationship(
        "MonitoringAlert",
        back_populates="research_event",
    )
