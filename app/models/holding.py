"""
Portfolio Health Monitor
Holding Model
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, ShortIdMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.portfolio import Portfolio


class Holding(Base, TimestampMixin, ShortIdMixin):
    """
    Position in a portfolio referencing a company asset.
    Contains position size, purchase metrics, and real-time valuation metrics.
    """
    __tablename__ = "holdings"
    __short_id_prefix__ = "hold"

    __table_args__ = (
        UniqueConstraint("portfolio_id", "company_id", name="uq_holdings_portfolio_company"),
        CheckConstraint("shares >= 0", name="ck_holdings_shares_positive"),
        CheckConstraint("average_buy_price >= 0", name="ck_holdings_buy_price_positive"),
    )

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
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    shares: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=6),
        nullable=False,
    )
    average_buy_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=False,
    )
    current_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    total_cost: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    market_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=18, scale=4),
        nullable=True,
    )
    weight_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=5, scale=2),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="holdings",
    )
    company: Mapped["Company"] = relationship(
        "Company",
        back_populates="holdings",
    )

