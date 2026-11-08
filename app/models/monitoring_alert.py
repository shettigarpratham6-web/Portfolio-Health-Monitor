"""
AgentX – Portfolio Health Monitor
Monitoring Alert Model
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.portfolio import Portfolio
    from app.models.research_event import ResearchEvent


class AlertType(str, Enum):
    """Types of portfolio monitoring alerts."""
    PORTFOLIO_RISK = "PORTFOLIO_RISK"
    HOLDING_VOLATILITY = "HOLDING_VOLATILITY"
    RESEARCH_UPDATE = "RESEARCH_UPDATE"
    DRIFT_WARNING = "DRIFT_WARNING"
    CRITICAL_EVENT = "CRITICAL_EVENT"


class AlertSeverity(str, Enum):
    """Urgency / severity of an alert."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    """Lifecycle status of a monitoring alert."""
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class MonitoringAlert(Base, TimestampMixin):
    """
    Actionable alert produced when risk thresholds are breached
    or significant corroborated research events impact portfolio holdings.
    """
    __tablename__ = "monitoring_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    research_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alert_type: Mapped[AlertType] = mapped_column(
        SQLEnum(AlertType, native_enum=False, length=50),
        default=AlertType.RESEARCH_UPDATE,
        nullable=False,
        index=True,
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        SQLEnum(AlertSeverity, native_enum=False, length=20),
        default=AlertSeverity.MEDIUM,
        nullable=False,
        index=True,
    )
    status: Mapped[AlertStatus] = mapped_column(
        SQLEnum(AlertStatus, native_enum=False, length=20),
        default=AlertStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="alerts",
    )
    company: Mapped[Optional["Company"]] = relationship(
        "Company",
        back_populates="alerts",
    )
    research_event: Mapped[Optional["ResearchEvent"]] = relationship(
        "ResearchEvent",
        back_populates="alerts",
    )

