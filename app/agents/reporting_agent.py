"""
Portfolio Health Monitor
Alert & Reporting Agent
Generates structured alerts with primary citations and persists reports via Database MCP tools.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from app.agents.impact_agent import PortfolioImpactReport
from app.agents.verification_agent import VerifiedEvent
from app.core.terminal_logger import TerminalLogger
from app.mcp.clients import get_mcp_client
from app.services.llm import get_llm_service

logger = logging.getLogger("agentx.agents.reporting")


# ------------------------------------------------------------------------------
# Input & Output Schemas
# ------------------------------------------------------------------------------
class ReportingAgentInput(BaseModel):
    """Input payload for Alert & Reporting Agent."""
    portfolio_id: str
    impact_report: PortfolioImpactReport
    verified_events: List[VerifiedEvent]
    persist_to_database: bool = True


class StructuredAlertItem(BaseModel):
    """Structured alert record detailing an event impact."""
    alert_id: Optional[str] = None
    portfolio_id: str
    ticker: Optional[str] = None
    title: str
    alert_type: str
    severity: str
    message: str
    affected_holdings: List[str] = Field(default_factory=list)
    evidence_sources: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    persisted: bool = False


class MonitoringReport(BaseModel):
    """Consolidated portfolio monitoring report."""
    portfolio_id: str
    report_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    executive_summary: str
    aggregate_risk_level: str
    alerts: List[StructuredAlertItem] = Field(default_factory=list)
    persisted_alerts_count: int = 0
    persisted_events_count: int = 0
    non_advisory_notice: str = (
        "Notice: This report provides objective risk and event monitoring only. "
        "It does NOT contain investment recommendations to buy, sell, or hold any financial security."
    )


# ------------------------------------------------------------------------------
# Reporting Agent
# ------------------------------------------------------------------------------
class ReportingAgent:
    """
    Alert & Reporting Agent.
    Formulates actionable, evidence-based alerts and persists verified records
    and alerts into the PostgreSQL database using Database MCP tools.
    """

    def __init__(self, mcp_client=None, llm_service=None) -> None:
        self.mcp = mcp_client or get_mcp_client()
        self.llm = llm_service or get_llm_service()

    @traceable(name="Alert & Reporting Agent", run_type="chain")
    async def run(self, input_data: ReportingAgentInput) -> MonitoringReport:
        """
        Synthesize monitoring alerts and persist records via Database MCP.
        """
        p_id = input_data.portfolio_id
        impact_report = input_data.impact_report
        events = input_data.verified_events
        persist = input_data.persist_to_database

        logger.info("Executing Reporting Agent for portfolio '%s'", p_id)

        # Map events by ticker
        events_by_ticker: Dict[str, List[VerifiedEvent]] = {}
        for ev in events:
            events_by_ticker.setdefault(ev.ticker.upper(), []).append(ev)

        persisted_events = 0
        persisted_alerts = 0
        event_db_ids: Dict[str, str] = {}  # event_hash -> db event_id

        # 1. Optionally persist verified events and primary sources to database
        if persist:
            for ev in events:
                if not ev.company_id:
                    continue
                try:
                    res_ev = await self.mcp.call_tool(
                        tool_name="save_research_event",
                        arguments={
                            "company_id": ev.company_id,
                            "title": ev.canonical_title,
                            "summary": ev.verified_summary,
                            "event_type": ev.event_type,
                            "severity": "HIGH" if ev.event_type in ("EARNINGS", "REGULATORY") else "MEDIUM",
                            "sentiment": ev.sentiment,
                            "verification_status": ev.verification_status,
                            "published_date": ev.published_date,
                            "event_hash": ev.event_hash,
                        },
                        server_name="database",
                    )
                    ev_db_id = res_ev.get("event_id")
                    if ev_db_id:
                        event_db_ids[ev.event_hash] = ev_db_id
                        persisted_events += 1
                        TerminalLogger.log_agent_step(f"↳ Saved event to PostgreSQL [{ev.ticker}]: \"{ev.canonical_title[:55]}\"")

                        # Also persist primary source citation
                        if ev.primary_source_url:
                            await self.mcp.call_tool(
                                tool_name="save_evidence_source",
                                arguments={
                                    "research_event_id": ev_db_id,
                                    "source_name": ev.source_name,
                                    "source_url": ev.primary_source_url,
                                    "publication_date": ev.published_date,
                                    "credibility_score": ev.credibility_score,
                                    "snippet": ev.verified_summary[:250],
                                },
                                server_name="database",
                            )
                            TerminalLogger.log_agent_step(f"  ↳ Citation: {ev.source_name} ({ev.primary_source_url[:45]}...)")
                except Exception as exc:
                    logger.warning("Failed to persist event '%s': %s", ev.canonical_title, exc)

        # 2. Generate structured alerts from significant impacts
        structured_alerts: List[StructuredAlertItem] = []

        for imp in impact_report.holding_impacts:
            # Generate alerts for medium, high, or critical severity impacts
            if imp.impact_severity in ("MEDIUM", "HIGH", "CRITICAL"):
                ev_list = events_by_ticker.get(imp.ticker.upper(), [])
                source_urls = [e.primary_source_url for e in ev_list if e.primary_source_url]
                first_ev = ev_list[0] if ev_list else None
                r_db_id = event_db_ids.get(first_ev.event_hash) if first_ev else None

                alert_type = (
                    "CRITICAL_EVENT" if imp.impact_severity == "CRITICAL"
                    else "HOLDING_VOLATILITY" if imp.direct_exposure and abs(imp.impact_score) >= 6.0
                    else "RESEARCH_UPDATE"
                )

                alert_title = f"{imp.impact_severity} Impact on {imp.ticker}: {imp.event_title[:60]}"
                alert_msg = (
                    f"Position {imp.ticker} ({imp.holding_weight_pct:.1f}% portfolio weight) "
                    f"is affected by verified {imp.event_type} event. "
                    f"Impact score: {imp.impact_score:+.1f}/10. Rationale: {imp.deterministic_rationale}"
                )

                alert_id = None
                persisted_status = False

                if persist:
                    try:
                        res_alert = await self.mcp.call_tool(
                            tool_name="save_monitoring_alert",
                            arguments={
                                "portfolio_id": p_id,
                                "title": alert_title,
                                "message": alert_msg,
                                "alert_type": alert_type,
                                "severity": imp.impact_severity,
                                "research_event_id": r_db_id,
                            },
                            server_name="database",
                        )
                        if res_alert.get("status") == "created":
                            alert_id = res_alert.get("alert_id")
                            persisted_status = True
                            persisted_alerts += 1
                            TerminalLogger.log_agent_step(f"↳ Persisted [{imp.impact_severity}] Alert on {imp.ticker}: \"{alert_title[:55]}\"")
                    except Exception as exc:
                        logger.warning("Failed to persist alert for %s: %s", imp.ticker, exc)

                structured_alerts.append(
                    StructuredAlertItem(
                        alert_id=alert_id,
                        portfolio_id=p_id,
                        ticker=imp.ticker,
                        title=alert_title,
                        alert_type=alert_type,
                        severity=imp.impact_severity,
                        message=alert_msg,
                        affected_holdings=[imp.ticker],
                        evidence_sources=source_urls,
                        confidence=0.9 if imp.direct_exposure else 0.7,
                        persisted=persisted_status,
                    )
                )

        exec_summary = (
            f"Health monitoring completed for portfolio '{impact_report.portfolio_name}'. "
            f"Evaluated {impact_report.total_events_evaluated} verified events. "
            f"Aggregate risk rating: {impact_report.aggregate_risk_level}. "
            f"Generated {len(structured_alerts)} actionable alerts."
        )

        return MonitoringReport(
            portfolio_id=p_id,
            executive_summary=exec_summary,
            aggregate_risk_level=impact_report.aggregate_risk_level,
            alerts=structured_alerts,
            persisted_alerts_count=persisted_alerts,
            persisted_events_count=persisted_events,
        )

