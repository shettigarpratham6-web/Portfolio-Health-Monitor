"""
AgentX – Portfolio Health Monitor
Database MCP Server
Exposes Controlled, Validated Database Access Tools via MCP (Zero Arbitrary SQL)
"""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import logging
from typing import Any, Dict, List, Optional
import uuid

from dateutil import parser as date_parser
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.database import AsyncSessionLocal
from app.models import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    Company,
    EventSentiment,
    EventSeverity,
    EvidenceSource,
    Holding,
    MonitoringAlert,
    Portfolio,
    ResearchEvent,
    ResearchEventType,
    VerificationStatus,
)

logger = logging.getLogger("agentx.mcp.database")

# ------------------------------------------------------------------------------
# Server Initialization
# ------------------------------------------------------------------------------
database_mcp = FastMCP(
    name="agentx-database",
    instructions=(
        "AgentX Database MCP Server: Provides controlled, parameterized CRUD tools "
        "to retrieve portfolios, query holdings, persist research events with deduplication, "
        "store primary evidence sources, and manage portfolio monitoring alerts."
    ),
)


# ------------------------------------------------------------------------------
# Tool Implementations
# ------------------------------------------------------------------------------
@database_mcp.tool(
    name="get_portfolio",
    description="Retrieve portfolio metadata, status, currency, and holdings summary by portfolio ID.",
)
async def get_portfolio(portfolio_id: str) -> Dict[str, Any]:
    """Retrieve detailed portfolio entity by UUID."""
    try:
        p_uuid = uuid.UUID(portfolio_id.strip())
    except ValueError:
        return {"status": "error", "message": f"Invalid UUID format for portfolio_id: '{portfolio_id}'."}

    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(Portfolio)
                .options(selectinload(Portfolio.holdings))
                .where(Portfolio.id == p_uuid)
            )
            result = await session.execute(stmt)
            portfolio = result.scalars().first()

            if not portfolio:
                return {"status": "not_found", "message": f"Portfolio '{portfolio_id}' not found."}

            holdings_count = len(portfolio.holdings)
            total_market_val = sum(
                (h.market_value for h in portfolio.holdings if h.market_value is not None),
                Decimal("0.0000"),
            )

            return {
                "status": "success",
                "portfolio": {
                    "id": str(portfolio.id),
                    "user_id": str(portfolio.user_id),
                    "name": portfolio.name,
                    "description": portfolio.description,
                    "currency": portfolio.currency,
                    "is_active": portfolio.is_active,
                    "holdings_count": holdings_count,
                    "total_market_value": str(total_market_val),
                    "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
                    "updated_at": portfolio.updated_at.isoformat() if portfolio.updated_at else None,
                },
            }
    except Exception as exc:
        logger.error("get_portfolio failed for '%s': %s", portfolio_id, exc)
        return {"status": "error", "message": f"Database query failed: {str(exc)}"}


@database_mcp.tool(
    name="get_holdings",
    description="Retrieve all stock and equity position holdings for a given portfolio.",
)
async def get_holdings(portfolio_id: str) -> Dict[str, Any]:
    """Retrieve all active equity holdings within a specified portfolio."""
    try:
        p_uuid = uuid.UUID(portfolio_id.strip())
    except ValueError:
        return {"status": "error", "message": f"Invalid UUID format for portfolio_id: '{portfolio_id}'."}

    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(Holding)
                .options(joinedload(Holding.company))
                .where(Holding.portfolio_id == p_uuid)
                .order_by(Holding.market_value.desc().nullslast())
            )
            result = await session.execute(stmt)
            holdings = result.scalars().all()

            holdings_data: List[Dict[str, Any]] = []
            for h in holdings:
                holdings_data.append(
                    {
                        "holding_id": str(h.id),
                        "company_id": str(h.company_id),
                        "ticker": h.company.ticker if h.company else None,
                        "company_name": h.company.name if h.company else None,
                        "sector": h.company.sector if h.company else None,
                        "shares": str(h.shares),
                        "average_buy_price": str(h.average_buy_price),
                        "current_price": str(h.current_price) if h.current_price is not None else None,
                        "market_value": str(h.market_value) if h.market_value is not None else None,
                        "weight_pct": str(h.weight_pct) if h.weight_pct is not None else None,
                    }
                )

            return {
                "status": "success",
                "portfolio_id": str(p_uuid),
                "count": len(holdings_data),
                "holdings": holdings_data,
            }
    except Exception as exc:
        logger.error("get_holdings failed for '%s': %s", portfolio_id, exc)
        return {"status": "error", "message": f"Database query failed: {str(exc)}"}


@database_mcp.tool(
    name="save_research_event",
    description="Save a verified or discovered financial research event with automatic deduplication.",
)
async def save_research_event(
    company_id: str,
    title: str,
    summary: str,
    event_type: str = "OTHER",
    severity: str = "MEDIUM",
    sentiment: str = "NEUTRAL",
    impact_score: Optional[float] = None,
    verification_status: str = "UNVERIFIED",
    published_date: Optional[str] = None,
    event_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a research event with SHA-256 deduplication to prevent duplicate entries."""
    try:
        comp_uuid = uuid.UUID(company_id.strip())
    except ValueError:
        return {"status": "error", "message": f"Invalid UUID format for company_id: '{company_id}'."}

    # Validate or compute deduplication hash
    if not event_hash:
        clean_title = title.strip().lower()
        clean_summary = summary.strip()[:100].lower()
        sig = f"{comp_uuid}:{event_type}:{clean_title}:{clean_summary}"
        event_hash = hashlib.sha256(sig.encode("utf-8")).hexdigest()

    # Parse publication timestamp if provided
    pub_dt: Optional[datetime] = None
    if published_date:
        try:
            pub_dt = date_parser.parse(published_date)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = None

    try:
        async with AsyncSessionLocal() as session:
            # Check for existing duplicate event by hash
            existing_stmt = select(ResearchEvent).where(ResearchEvent.event_hash == event_hash)
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                return {
                    "status": "duplicate",
                    "event_id": str(existing.id),
                    "event_hash": event_hash,
                    "title": existing.title,
                    "message": "Research event with matching content already exists in database.",
                }

            # Map enums safely with fallbacks
            try:
                ev_type = ResearchEventType(event_type.upper())
            except ValueError:
                ev_type = ResearchEventType.OTHER

            try:
                ev_sev = EventSeverity(severity.upper())
            except ValueError:
                ev_sev = EventSeverity.MEDIUM

            try:
                ev_sent = EventSentiment(sentiment.upper())
            except ValueError:
                ev_sent = EventSentiment.NEUTRAL

            try:
                v_stat = VerificationStatus(verification_status.upper())
            except ValueError:
                v_stat = VerificationStatus.UNVERIFIED

            imp_dec = Decimal(str(impact_score)) if impact_score is not None else None

            event = ResearchEvent(
                company_id=comp_uuid,
                event_hash=event_hash,
                title=title.strip(),
                summary=summary.strip(),
                event_type=ev_type,
                severity=ev_sev,
                sentiment=ev_sent,
                impact_score=imp_dec,
                verification_status=v_stat,
                published_date=pub_dt,
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)

            return {
                "status": "created",
                "event_id": str(event.id),
                "event_hash": event_hash,
                "title": event.title,
                "verification_status": event.verification_status.value,
            }
    except Exception as exc:
        logger.error("save_research_event failed: %s", exc)
        return {"status": "error", "message": f"Failed to persist research event: {str(exc)}"}


@database_mcp.tool(
    name="save_evidence_source",
    description="Save a primary corroborating source citation (e.g., SEC filing, news article) for a research event.",
)
async def save_evidence_source(
    research_event_id: str,
    source_name: str,
    source_url: str,
    publication_date: Optional[str] = None,
    author: Optional[str] = None,
    snippet: Optional[str] = None,
    credibility_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Persist a primary evidence citation linked to a ResearchEvent."""
    try:
        ev_uuid = uuid.UUID(research_event_id.strip())
    except ValueError:
        return {"status": "error", "message": f"Invalid UUID format for research_event_id: '{research_event_id}'."}

    pub_dt: Optional[datetime] = None
    if publication_date:
        try:
            pub_dt = date_parser.parse(publication_date)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = None

    try:
        async with AsyncSessionLocal() as session:
            # Check unique constraint (research_event_id, source_url)
            stmt = select(EvidenceSource).where(
                EvidenceSource.research_event_id == ev_uuid,
                EvidenceSource.source_url == source_url.strip(),
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                return {
                    "status": "exists",
                    "evidence_id": str(existing.id),
                    "message": "Source citation already recorded for this event.",
                }

            cred_dec = Decimal(str(credibility_score)) if credibility_score is not None else None

            source = EvidenceSource(
                research_event_id=ev_uuid,
                source_name=source_name.strip(),
                source_url=source_url.strip(),
                publication_date=pub_dt,
                author=author.strip() if author else None,
                snippet=snippet.strip() if snippet else None,
                credibility_score=cred_dec,
            )
            session.add(source)
            await session.commit()
            await session.refresh(source)

            return {
                "status": "created",
                "evidence_id": str(source.id),
                "research_event_id": str(source.research_event_id),
                "source_url": source.source_url,
            }
    except Exception as exc:
        logger.error("save_evidence_source failed: %s", exc)
        return {"status": "error", "message": f"Failed to persist evidence source: {str(exc)}"}


@database_mcp.tool(
    name="save_monitoring_alert",
    description="Save an actionable portfolio alert produced by AgentX monitoring workflows.",
)
async def save_monitoring_alert(
    portfolio_id: str,
    title: str,
    message: str,
    alert_type: str = "RESEARCH_UPDATE",
    severity: str = "MEDIUM",
    company_id: Optional[str] = None,
    research_event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create and persist an alert for an investment portfolio."""
    try:
        p_uuid = uuid.UUID(portfolio_id.strip())
        c_uuid = uuid.UUID(company_id.strip()) if company_id else None
        r_uuid = uuid.UUID(research_event_id.strip()) if research_event_id else None
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid UUID argument: {str(exc)}"}

    try:
        async with AsyncSessionLocal() as session:
            try:
                a_type = AlertType(alert_type.upper())
            except ValueError:
                a_type = AlertType.RESEARCH_UPDATE

            try:
                a_sev = AlertSeverity(severity.upper())
            except ValueError:
                a_sev = AlertSeverity.MEDIUM

            alert = MonitoringAlert(
                portfolio_id=p_uuid,
                company_id=c_uuid,
                research_event_id=r_uuid,
                alert_type=a_type,
                severity=a_sev,
                status=AlertStatus.ACTIVE,
                title=title.strip(),
                message=message.strip(),
            )
            session.add(alert)
            await session.commit()
            await session.refresh(alert)

            return {
                "status": "created",
                "alert_id": str(alert.id),
                "portfolio_id": str(alert.portfolio_id),
                "severity": alert.severity.value,
                "status_code": alert.status.value,
            }
    except Exception as exc:
        logger.error("save_monitoring_alert failed: %s", exc)
        return {"status": "error", "message": f"Failed to persist alert: {str(exc)}"}


@database_mcp.tool(
    name="get_previous_alerts",
    description="Retrieve historical monitoring alerts for a portfolio or specific company.",
)
async def get_previous_alerts(
    portfolio_id: str,
    limit: int = 10,
    company_id: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch recent monitoring alerts ordered by creation time descending."""
    try:
        p_uuid = uuid.UUID(portfolio_id.strip())
        c_uuid = uuid.UUID(company_id.strip()) if company_id else None
    except ValueError as exc:
        return {"status": "error", "message": f"Invalid UUID: {str(exc)}"}

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(MonitoringAlert).where(MonitoringAlert.portfolio_id == p_uuid)
            if c_uuid:
                stmt = stmt.where(MonitoringAlert.company_id == c_uuid)
            if status:
                try:
                    a_stat = AlertStatus(status.upper())
                    stmt = stmt.where(MonitoringAlert.status == a_stat)
                except ValueError:
                    pass

            stmt = stmt.order_by(MonitoringAlert.created_at.desc()).limit(min(limit, 50))
            result = await session.execute(stmt)
            alerts = result.scalars().all()

            return {
                "status": "success",
                "portfolio_id": str(p_uuid),
                "count": len(alerts),
                "alerts": [
                    {
                        "id": str(a.id),
                        "portfolio_id": str(a.portfolio_id),
                        "company_id": str(a.company_id) if a.company_id else None,
                        "research_event_id": str(a.research_event_id) if a.research_event_id else None,
                        "alert_type": a.alert_type.value,
                        "severity": a.severity.value,
                        "status": a.status.value,
                        "title": a.title,
                        "message": a.message,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in alerts
                ],
            }
    except Exception as exc:
        logger.error("get_previous_alerts failed: %s", exc)
        return {"status": "error", "message": f"Database query failed: {str(exc)}"}


if __name__ == "__main__":
    database_mcp.run()

