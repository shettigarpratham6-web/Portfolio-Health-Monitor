"""
AgentX – Portfolio Health Monitor
Portfolio Impact Agent
Calculates deterministic impact scores and maps verified events to portfolio equity holdings.
"""

import logging
from typing import Any, Dict, List, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from app.agents.portfolio_agent import PortfolioContext
from app.agents.verification_agent import VerifiedEvent
from app.mcp.clients import get_mcp_client
from app.services.llm import get_llm_service

logger = logging.getLogger("agentx.agents.impact")


# ------------------------------------------------------------------------------
# Input & Output Schemas
# ------------------------------------------------------------------------------
class ImpactAgentInput(BaseModel):
    """Input payload for Portfolio Impact Agent."""
    portfolio_context: PortfolioContext
    verified_events: List[VerifiedEvent]


class HoldingImpact(BaseModel):
    """Deterministic impact assessment for a specific portfolio holding."""
    ticker: str
    company_name: str
    holding_weight_pct: float
    holding_market_value: float
    direct_exposure: bool
    indirect_exposure_reason: Optional[str] = None
    event_title: str
    event_type: str
    impact_direction: str  # POSITIVE, NEGATIVE, NEUTRAL, UNCERTAIN
    impact_severity: str   # LOW, MEDIUM, HIGH, CRITICAL
    impact_score: float = Field(ge=-10.0, le=10.0, description="Directional impact score from -10 to +10")
    weighted_portfolio_risk: float = Field(description="Impact scaled by portfolio position weight")
    deterministic_rationale: str


class PortfolioImpactReport(BaseModel):
    """Aggregated portfolio impact report."""
    portfolio_id: str
    portfolio_name: str
    total_events_evaluated: int
    direct_impacts_count: int
    indirect_impacts_count: int
    aggregate_risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    highest_impact_holding: Optional[str] = None
    holding_impacts: List[HoldingImpact] = Field(default_factory=list)
    impact_summary: str
    non_advisory_disclaimer: str = (
        "Notice: This report provides objective risk and event monitoring only. "
        "It does NOT contain investment recommendations to buy, sell, or hold any financial security."
    )


# ------------------------------------------------------------------------------
# Impact Agent
# ------------------------------------------------------------------------------
class ImpactAgent:
    """
    Portfolio Impact Agent.
    Evaluates verified events against current portfolio holdings using
    transparent, deterministic scoring rules and Analysis MCP exposure metrics.
    """

    SEVERITY_WEIGHTS = {
        "CRITICAL": 10.0,
        "HIGH": 7.0,
        "MEDIUM": 4.0,
        "LOW": 2.0,
    }

    POLARITY_MULTIPLIERS = {
        "BULLISH": 1.0,
        "POSITIVE": 1.0,
        "BEARISH": -1.0,
        "NEGATIVE": -1.0,
        "NEUTRAL": 0.0,
        "UNKNOWN": 0.0,
    }

    def __init__(self, mcp_client=None, llm_service=None) -> None:
        self.mcp = mcp_client or get_mcp_client()
        self.llm = llm_service or get_llm_service()

    @traceable(name="Portfolio Impact Agent", run_type="chain")
    async def run(self, input_data: ImpactAgentInput) -> PortfolioImpactReport:
        """
        Execute deterministic impact analysis.
        Maps each verified event to affected holdings and determines direct/indirect exposure.
        """
        p_ctx = input_data.portfolio_context
        events = input_data.verified_events
        logger.info(
            "Executing Impact Agent for portfolio '%s' with %d events",
            p_ctx.portfolio_id,
            len(events),
        )

        # Index holdings by ticker for fast lookup
        holdings_by_ticker = {h.ticker.upper(): h for h in p_ctx.holdings}
        holdings_by_sector: Dict[str, List[Any]] = {}
        for h in p_ctx.holdings:
            holdings_by_sector.setdefault(h.sector.upper(), []).append(h)

        impacts: List[HoldingImpact] = []
        direct_count = 0
        indirect_count = 0

        for ev in events:
            ev_ticker = ev.ticker.upper()
            base_severity = self.SEVERITY_WEIGHTS.get(ev.event_type.upper(), 5.0)
            polarity = self.POLARITY_MULTIPLIERS.get(ev.sentiment.upper(), 0.0)

            # 1. Direct Exposure Evaluation
            if ev_ticker in holdings_by_ticker:
                holding = holdings_by_ticker[ev_ticker]
                direct_count += 1

                # Deterministic scoring: Severity scaled by holding concentration
                weight_factor = 1.0 + (holding.weight_pct / 25.0)
                score = round(max(-10.0, min(10.0, polarity * base_severity * weight_factor)), 2)
                weighted_risk = round(abs(score) * (holding.weight_pct / 100.0), 3)

                # Classify severity level based on weighted score
                if abs(score) >= 7.5 or weighted_risk >= 2.0:
                    severity_label = "CRITICAL"
                elif abs(score) >= 5.0 or weighted_risk >= 1.0:
                    severity_label = "HIGH"
                elif abs(score) >= 2.5:
                    severity_label = "MEDIUM"
                else:
                    severity_label = "LOW"

                direction = (
                    "POSITIVE" if score > 0.5
                    else "NEGATIVE" if score < -0.5
                    else "NEUTRAL"
                )

                rationale = (
                    f"Direct exposure of {holding.weight_pct:.1f}% (${holding.market_value:,.2f}) "
                    f"to verified '{ev.event_type}' event with {ev.sentiment} sentiment. "
                    f"Weighted portfolio risk contribution: {weighted_risk:.2f}."
                )

                impacts.append(
                    HoldingImpact(
                        ticker=holding.ticker,
                        company_name=holding.company_name,
                        holding_weight_pct=holding.weight_pct,
                        holding_market_value=holding.market_value,
                        direct_exposure=True,
                        indirect_exposure_reason=None,
                        event_title=ev.canonical_title,
                        event_type=ev.event_type,
                        impact_direction=direction,
                        impact_severity=severity_label,
                        impact_score=score,
                        weighted_portfolio_risk=weighted_risk,
                        deterministic_rationale=rationale,
                    )
                )

            # 2. Indirect Sector/Competitor Exposure Evaluation
            else:
                # Check if other holdings share the same sector
                for h in p_ctx.holdings:
                    # Check sector overlap if event is macro or regulatory
                    if ev.event_type in ("MACRO", "REGULATORY") and h.sector != "Unknown":
                        indirect_count += 1
                        dampened_score = round(polarity * base_severity * 0.35, 2)
                        weighted_risk = round(abs(dampened_score) * (h.weight_pct / 100.0), 3)

                        impacts.append(
                            HoldingImpact(
                                ticker=h.ticker,
                                company_name=h.company_name,
                                holding_weight_pct=h.weight_pct,
                                holding_market_value=h.market_value,
                                direct_exposure=False,
                                indirect_exposure_reason=(
                                    f"Industry peer correlation: {ev.company_name} ({ev.ticker}) event "
                                    f"has macro/regulatory implications for {h.sector} sector."
                                ),
                                event_title=ev.canonical_title,
                                event_type=ev.event_type,
                                impact_direction="NEUTRAL" if dampened_score == 0 else ("POSITIVE" if dampened_score > 0 else "NEGATIVE"),
                                impact_severity="LOW" if abs(dampened_score) < 3.0 else "MEDIUM",
                                impact_score=dampened_score,
                                weighted_portfolio_risk=weighted_risk,
                                deterministic_rationale=f"Indirect peer effect dampened to 35% of primary severity.",
                            )
                        )

        # 3. Aggregate Portfolio Risk Level
        total_weighted_risk = sum(imp.weighted_portfolio_risk for imp in impacts)
        if total_weighted_risk >= 3.0 or any(imp.impact_severity == "CRITICAL" for imp in impacts):
            overall_risk = "CRITICAL"
        elif total_weighted_risk >= 1.5 or any(imp.impact_severity == "HIGH" for imp in impacts):
            overall_risk = "HIGH"
        elif total_weighted_risk >= 0.5:
            overall_risk = "MEDIUM"
        else:
            overall_risk = "LOW"

        highest_impact = max(impacts, key=lambda x: abs(x.impact_score)).ticker if impacts else None

        summary = (
            f"Impact evaluation complete for '{p_ctx.name}': {len(impacts)} impacts mapped "
            f"({direct_count} direct, {indirect_count} indirect). "
            f"Aggregate portfolio risk is assessed at {overall_risk}. "
            f"Most affected holding: {highest_impact or 'None'}."
        )

        return PortfolioImpactReport(
            portfolio_id=p_ctx.portfolio_id,
            portfolio_name=p_ctx.name,
            total_events_evaluated=len(events),
            direct_impacts_count=direct_count,
            indirect_impacts_count=indirect_count,
            aggregate_risk_level=overall_risk,
            highest_impact_holding=highest_impact,
            holding_impacts=impacts,
            impact_summary=summary,
        )

