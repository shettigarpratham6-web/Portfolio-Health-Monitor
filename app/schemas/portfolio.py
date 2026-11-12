"""
Portfolio Health Monitor
Pydantic v2 Schemas for Portfolio API
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortfolioBase(BaseModel):
    """Base portfolio attributes."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Descriptive portfolio name",
        examples=["Global Tech Strategy", "Dividend Growth Fund"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional portfolio investment thesis or notes",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="Three-letter ISO currency code (e.g., USD, EUR, GBP)",
        examples=["USD"],
    )

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Portfolio name cannot be empty or whitespace only.")
        return trimmed

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        upper = v.strip().upper()
        if not upper.isalpha() or len(upper) != 3:
            raise ValueError("Currency must be a 3-letter alphabetic ISO code.")
        return upper


class PortfolioCreate(PortfolioBase):
    """
    Payload for creating a new portfolio.
    Notice: Does NOT accept user_id from client; identity is derived exclusively
    from the authenticated session to maintain strict security boundaries.
    """
    model_config = ConfigDict(extra="forbid")


class PortfolioUpdate(BaseModel):
    """Payload for updating an existing portfolio."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = Field(default=None, max_length=1000)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def clean_update_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("Portfolio name cannot be blank.")
            return trimmed
        return None

    @field_validator("currency")
    @classmethod
    def normalize_update_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            upper = v.strip().upper()
            if not upper.isalpha() or len(upper) != 3:
                raise ValueError("Currency must be a 3-letter alphabetic ISO code.")
            return upper
        return None


class HoldingCreate(BaseModel):
    """Payload to add a new asset holding position to a portfolio."""
    ticker: str = Field(..., min_length=1, max_length=10, description="Asset ticker symbol, e.g. NVDA, AAPL")
    company_name: Optional[str] = Field(default=None, max_length=255, description="Full legal corporate name")
    shares: Decimal = Field(..., gt=0, description="Quantity of shares owned (must be > 0)")
    average_buy_price: Decimal = Field(..., gt=0, description="Average cost basis per share (must be > 0)")
    current_price: Optional[Decimal] = Field(default=None, gt=0, description="Latest market price per share")
    notes: Optional[str] = Field(default=None, max_length=500, description="Position thesis or notes")

    model_config = ConfigDict(extra="forbid")

    @field_validator("ticker")
    @classmethod
    def clean_ticker(cls, v: str) -> str:
        trimmed = v.strip().upper()
        if not trimmed:
            raise ValueError("Ticker cannot be empty.")
        return trimmed


class HoldingSummary(BaseModel):
    """Summary of a single holding within a portfolio."""
    id: uuid.UUID
    short_id: Optional[str] = None
    company_id: uuid.UUID
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    shares: Decimal
    average_buy_price: Decimal
    current_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    weight_pct: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class PortfolioResponse(PortfolioBase):
    """Summary representation of a portfolio returned in listings and creations."""
    id: uuid.UUID
    short_id: Optional[str] = None
    user_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    holdings_count: int = Field(default=0, description="Total count of company positions in portfolio")
    total_market_value: Optional[Decimal] = Field(
        default=None,
        description="Calculated total market value of all held assets",
    )

    model_config = ConfigDict(from_attributes=True)


class PortfolioDetailResponse(PortfolioResponse):
    """Detailed representation of a portfolio including embedded holdings."""
    holdings: List[HoldingSummary] = Field(
        default_factory=list,
        description="Active position holdings in this portfolio",
    )


class PaginatedPortfolioResponse(BaseModel):
    """Paginated list of user portfolios."""
    items: List[PortfolioResponse] = Field(description="Portfolios on the current page")
    total: int = Field(ge=0, description="Total number of portfolios matching query")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, description="Number of items per page")
    total_pages: int = Field(ge=0, description="Total available pages")
    has_next: bool = Field(description="Whether a next page exists")
    has_prev: bool = Field(description="Whether a previous page exists")


class ErrorResponse(BaseModel):
    """Standardized error response schema."""
    detail: str = Field(description="Human-readable error explanation")
    error_code: Optional[str] = Field(default=None, description="Optional machine-readable error classification")


class MonitoringTriggerRequest(BaseModel):
    """Payload to trigger an autonomous LangGraph monitoring run on a portfolio."""
    specific_tickers: Optional[List[str]] = Field(default=None, description="Optional subset of tickers to monitor")
    max_news_per_target: int = Field(default=3, ge=1, le=10)
    max_filings_per_target: int = Field(default=2, ge=0, le=5)
    include_filings: bool = True
    include_news: bool = True
    persist_alerts: bool = True


class AlertStatusUpdate(BaseModel):
    """Payload to update an alert's lifecycle status."""
    status: str = Field(..., description="Target status: ACKNOWLEDGED, RESOLVED, or ACTIVE")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        upper = v.strip().upper()
        if upper not in ("ACTIVE", "ACKNOWLEDGED", "RESOLVED"):
            raise ValueError("Status must be one of: ACTIVE, ACKNOWLEDGED, RESOLVED")
        return upper


class MonitoringAlertResponse(BaseModel):
    """Schema for persisted monitoring alert records."""
    id: uuid.UUID
    short_id: Optional[str] = None
    portfolio_id: uuid.UUID
    title: str
    message: str
    alert_type: str
    severity: str
    status: str
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DiscoveredEventItem(BaseModel):
    """Structured record of an event or filing discovered from research."""
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    company_id: Optional[str] = None
    title: str
    url: Optional[str] = None
    source_name: Optional[str] = None
    publication_date: Optional[str] = None
    snippet: Optional[str] = None
    event_category: Optional[str] = None
    relevance_score: Optional[float] = None


class VerifiedEventItem(BaseModel):
    """Corroborated and verified event with primary citations and fact separation."""
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    company_id: Optional[str] = None
    canonical_title: str
    verified_summary: str
    event_type: Optional[str] = None
    sentiment: Optional[str] = None
    verification_status: Optional[str] = None
    credibility_score: Optional[float] = None
    primary_source_url: Optional[str] = None
    source_name: Optional[str] = None
    published_date: Optional[str] = None
    facts: List[Any] = Field(default_factory=list)
    speculative_claims: List[Any] = Field(default_factory=list)


class HoldingImpactItem(BaseModel):
    """Deterministic holding exposure and risk evaluation."""
    ticker: str
    company_name: str
    holding_weight_pct: Optional[float] = None
    holding_market_value: Optional[float] = None
    direct_exposure: bool = True
    indirect_exposure_reason: Optional[str] = None
    event_title: str
    event_type: str
    impact_direction: str
    impact_severity: str
    impact_score: Optional[float] = None
    weighted_portfolio_risk: Optional[float] = None
    deterministic_rationale: Optional[str] = None


class StructuredAlertSummaryItem(BaseModel):
    """Structured alert record detailing an event impact."""
    alert_id: Optional[str] = None
    ticker: Optional[str] = None
    title: str
    alert_type: str
    severity: str
    message: str
    affected_holdings: List[str] = Field(default_factory=list)
    evidence_sources: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class MonitoringRunResponse(BaseModel):
    """API response model for completed or partial portfolio monitoring workflow."""
    status: str
    portfolio_id: str
    completed_at: Optional[str] = None
    executive_summary: Optional[str] = None
    aggregate_risk_level: Optional[str] = None
    alerts_generated_count: int = 0
    persisted_alerts_count: int = 0
    errors: List[str] = Field(default_factory=list)
    non_advisory_notice: str
    discovery_summary: Optional[str] = None
    verification_summary: Optional[str] = None
    impact_summary: Optional[str] = None
    discovered_events: List[DiscoveredEventItem] = Field(default_factory=list)
    verified_events: List[VerifiedEventItem] = Field(default_factory=list)
    holding_impacts: List[HoldingImpactItem] = Field(default_factory=list)
    alerts: List[StructuredAlertSummaryItem] = Field(default_factory=list)


class PortfolioChatRequest(BaseModel):
    """Payload to ask an interactive natural language question about a portfolio."""
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language investor query")
    history: Optional[List[Dict[str, str]]] = Field(default=None, description="Optional prior conversation turns")

    @field_validator("query")
    @classmethod
    def clean_query(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Query cannot be empty.")
        return trimmed


class PortfolioChatResponse(BaseModel):
    """Response from the Portfolio Health Monitor AI Copilot."""
    portfolio_id: str
    portfolio_name: str
    query: str
    answer: str
    cited_holdings: List[str] = Field(default_factory=list)
    confidence: str = "HIGH"
    non_advisory_notice: str


