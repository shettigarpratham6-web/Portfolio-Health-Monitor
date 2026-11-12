"""
Portfolio Health Monitor
Portfolio Model
"""

from typing import TYPE_CHECKING, List, Optional
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, ShortIdMixin

if TYPE_CHECKING:
    from app.models.holding import Holding
    from app.models.monitoring_alert import MonitoringAlert
    from app.models.user import User


class Portfolio(Base, TimestampMixin, ShortIdMixin):
    """
    Portfolio entity owned by a user.
    Houses multiple stock holdings and monitors health, risks, and alerts.
    """
    __tablename__ = "portfolios"
    __short_id_prefix__ = "port"

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_portfolios_user_id_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="portfolios",
    )
    holdings: Mapped[List["Holding"]] = relationship(
        "Holding",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    alerts: Mapped[List["MonitoringAlert"]] = relationship(
        "MonitoringAlert",
        back_populates="portfolio",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

