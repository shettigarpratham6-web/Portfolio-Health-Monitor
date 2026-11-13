"""
Portfolio Health Monitor
Portfolio Impact Agent
Calculates deterministic impact scores and maps verified events to portfolio equity holdings.
"""

import logging
from typing import Any, Dict, List, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from app.agents.portfolio_agent import PortfolioContext
from app.agents.verification_agent import VerifiedEvent
from app.core.terminal_logger import TerminalLogger
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
    risk_flag: str = Field(default="BALANCED", description="Data-driven categorical risk flag")
    evidence_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Evidentiary confidence factor")


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

    EVENT_TYPE_BASE_SEVERITY = {
        "LITIGATION": 8.5,
        "REGULATORY": 8.0,
        "EARNINGS": 7.5,
        "MACRO": 7.0,
        "LEADERSHIP": 5.0,
        "PRODUCT": 4.5,
        "OTHER": 3.5,
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

    @staticmethod
    def _calculate_evidence_confidence(ev: VerifiedEvent) -> float:
        """Calculate evidentiary confidence weight based on credibility, verification status, and corroborated facts."""
        credibility = max(0.1, min(1.0, ev.credibility_score))
        status = (ev.verification_status or "").upper()
        status_mult = 1.0 if status == "VERIFIED" else (
            0.65 if status == "UNVERIFIED" else (
                0.40 if status == "INCONCLUSIVE" else 0.05
            )
        )
        facts_count = len(ev.facts) if ev.facts else 0
        spec_count = len(ev.speculative_claims) if ev.speculative_claims else 0
        corroboration_factor = min(1.10, max(0.70, 0.90 + (0.05 * facts_count) - (0.05 * spec_count)))
        return round(max(0.1, min(1.0, credibility * status_mult * corroboration_factor)), 2)

    @traceable(name="Portfolio Impact Agent", run_type="chain")
    async def run(self, input_data: ImpactAgentInput) -> PortfolioImpactReport:
        """
        Execute deterministic impact analysis.
        Maps each verified event to affected holdings and computes accurate,
        data-driven impact scores and risk flags.
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
            base_severity = self.EVENT_TYPE_BASE_SEVERITY.get(ev.event_type.upper(), 5.0)
            polarity = self.POLARITY_MULTIPLIERS.get(ev.sentiment.upper(), 0.0)
            ev_confidence = self._calculate_evidence_confidence(ev)

            # 1. Direct Exposure Evaluation
            if ev_ticker in holdings_by_ticker:
                holding = holdings_by_ticker[ev_ticker]
                direct_count += 1

                # Deterministic asset impact score (-10.0 to +10.0) based on actual evidence
                score = round(max(-10.0, min(10.0, polarity * base_severity * ev_confidence)), 2)

                direction = (
                    "POSITIVE" if score > 0.5
                    else "NEGATIVE" if score < -0.5
                    else "NEUTRAL"
                )

                # Portfolio-level weighted downside risk calculation
                holding_weight = holding.weight_pct / 100.0
                conc_multiplier = 1.30 if holding.weight_pct >= 25.0 else (1.15 if holding.weight_pct >= 15.0 else 1.0)

                if direction == "NEGATIVE":
                    # Adverse event generates real downside portfolio risk
                    weighted_risk = round(abs(score) * holding_weight * conc_multiplier, 3)

                    # Classify severity and risk flags based on data-driven thresholds
                    if abs(score) >= 6.5 and (weighted_risk >= 1.5 or holding.weight_pct >= 25.0):
                        severity_label = "CRITICAL"
                        risk_flag = "CRITICAL_CONCENTRATION_RISK" if holding.weight_pct >= 25.0 else "CRITICAL_RISK"
                    elif abs(score) >= 4.5 or weighted_risk >= 0.8:
                        severity_label = "HIGH"
                        risk_flag = "HIGH_EXPOSURE_RISK" if holding.weight_pct >= 15.0 else "HIGH_RISK"
                    elif abs(score) >= 2.0 or weighted_risk >= 0.3:
                        severity_label = "MEDIUM"
                        risk_flag = "MODERATE_RISK"
                    else:
                        severity_label = "LOW"
                        risk_flag = "LOW_RISK"

                    rationale = (
                        f"Direct holding exposure of {holding.weight_pct:.1f}% (${holding.market_value:,.2f}) "
                        f"to adverse '{ev.event_type}' event (Score: {score:.1f}/10, Evidence Confidence: {ev_confidence*100:.0f}%). "
                        f"Weighted portfolio downside risk factor: {weighted_risk:.2f}. "
                        f"{'Amplified by high position concentration.' if holding.weight_pct >= 25.0 else ''}"
                    ).strip()

                elif direction == "POSITIVE":
                    # Positive catalysts represent opportunities, not capital loss risk
                    weighted_risk = 0.0
                    severity_label = "LOW"
                    risk_flag = "STRONG_POSITIVE_CATALYST" if score >= 6.0 else "FAVORABLE_CATALYST"
                    rationale = (
                        f"Direct holding of {holding.weight_pct:.1f}% (${holding.market_value:,.2f}) "
                        f"benefits from favorable '{ev.event_type}' catalyst (Score: +{score:.1f}/10, Evidence Confidence: {ev_confidence*100:.0f}%). "
                        f"Favorable growth catalyst with 0.00 adverse downside risk."
                    )
                else:
                    weighted_risk = 0.0
                    severity_label = "LOW"
                    risk_flag = "NEUTRAL"
                    rationale = (
                        f"Direct holding of {holding.weight_pct:.1f}% (${holding.market_value:,.2f}) "
                        f"evaluated for neutral '{ev.event_type}' event. Neutral catalyst with 0.00 adverse downside risk."
                    )

                TerminalLogger.log_agent_step(
                    f"↳ Direct Impact on {holding.ticker}: Score={score:+.1f}/10 ({direction}) | "
                    f"Severity={severity_label} | Risk Contrib={weighted_risk:.2f} | Flag={risk_flag}"
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
                        risk_flag=risk_flag,
                        evidence_confidence=ev_confidence,
                    )
                )

            # 2. Indirect Sector/Competitor Exposure Evaluation
            else:
                for h in p_ctx.holdings:
                    if ev.event_type in ("MACRO", "REGULATORY") and h.sector != "Unknown":
                        indirect_count += 1
                        dampened_score = round(polarity * base_severity * ev_confidence * 0.35, 2)

                        if dampened_score < 0:
                            weighted_risk = round(abs(dampened_score) * (h.weight_pct / 100.0), 3)
                            severity = "MEDIUM" if abs(dampened_score) >= 2.5 else "LOW"
                            risk_flag = "SECTOR_CONTAGION_RISK" if abs(dampened_score) >= 2.0 else "LOW_RISK"
                            direction = "NEGATIVE"
                        elif dampened_score > 0:
                            weighted_risk = 0.0
                            severity = "LOW"
                            risk_flag = "SECTOR_TAILWIND"
                            direction = "POSITIVE"
                        else:
                            weighted_risk = 0.0
                            severity = "LOW"
                            risk_flag = "NEUTRAL"
                            direction = "NEUTRAL"

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
                                impact_direction=direction,
                                impact_severity=severity,
                                impact_score=dampened_score,
                                weighted_portfolio_risk=weighted_risk,
                                deterministic_rationale=f"Indirect peer effect dampened to 35% of primary severity with {ev_confidence*100:.0f}% evidence confidence.",
                                risk_flag=risk_flag,
                                evidence_confidence=ev_confidence,
                            )
                        )

        # 3. Aggregate Portfolio Risk Level (strictly based on adverse downside risks)
        adverse_impacts = [imp for imp in impacts if imp.impact_direction == "NEGATIVE"]
        total_adverse_risk = sum(imp.weighted_portfolio_risk for imp in adverse_impacts)
        has_critical = any(imp.impact_severity == "CRITICAL" for imp in adverse_impacts)
        has_high = any(imp.impact_severity == "HIGH" for imp in adverse_impacts)

        if has_critical or total_adverse_risk >= 3.0:
            overall_risk = "CRITICAL"
        elif has_high or total_adverse_risk >= 1.5:
            overall_risk = "HIGH"
        elif total_adverse_risk >= 0.5 or p_ctx.concentration_risk_level == "HIGH":
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

