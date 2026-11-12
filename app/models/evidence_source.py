"""
Portfolio Health Monitor
Evidence Source Model
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, ShortIdMixin

if TYPE_CHECKING:
    from app.models.research_event import ResearchEvent


class EvidenceSource(Base, TimestampMixin, ShortIdMixin):
    """
    Primary verifiable source citation corroborating a research event
    (e.g., SEC EDGAR 10-K/10-Q filing, Reuters, Bloomberg, Press Release).
    Preserves original source URLs, publication timestamps, and credibility ratings.
    """
    __tablename__ = "evidence_sources"
    __short_id_prefix__ = "src"

    __table_args__ = (
        UniqueConstraint("research_event_id", "source_url", name="uq_evidence_sources_event_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    research_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    publication_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    author: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    snippet: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    credibility_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=4, scale=2),
        nullable=True,
    )

    # Relationships
    research_event: Mapped["ResearchEvent"] = relationship(
        "ResearchEvent",
        back_populates="evidence_sources",
    )

