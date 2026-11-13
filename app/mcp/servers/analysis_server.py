"""
Portfolio Health Monitor
Analysis MCP Server
Exposes Financial Analytics, Portfolio Allocation, Exposure & Event Deduplication Tools via MCP
"""

from decimal import Decimal
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Set
import uuid

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import AsyncSessionLocal
from app.models import Company, Holding, Portfolio, ResearchEvent

logger = logging.getLogger("agentx.mcp.analysis")

# ------------------------------------------------------------------------------
# Server Initialization
# ------------------------------------------------------------------------------
analysis_mcp = FastMCP(
    name="agentx-analysis",
    instructions=(
        "AgentX Analysis MCP Server: Provides quantitative financial analysis tools "
        "including portfolio allocation calculation, single-company exposure assessment, "
        "evidence deduplication, and cross-holding sector relationship analysis."
    ),
)


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def _calculate_text_similarity(text_a: str, text_b: str) -> float:
    """Calculate token-based Jaccard similarity between two texts."""
    tokens_a = set(re.findall(r"\w+", text_a.lower()))
    tokens_b = set(re.findall(r"\w+", text_b.lower()))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    return len(intersection) / len(union)


# ------------------------------------------------------------------------------
# Tool Implementations
# ------------------------------------------------------------------------------
@analysis_mcp.tool(
    name="calculate_portfolio_allocation",
    description="Calculate asset weights, total valuation, unrealized returns, and concentration risk metrics.",
)
async def calculate_portfolio_allocation(
    portfolio_id: Optional[str] = None,
    holdings_data: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Calculate portfolio weight allocation, total market value, unrealized gain/loss,
    and concentration risk using Herfindahl-Hirschman Index (HHI).
    """
    positions: List[Dict[str, Any]] = []

    # If holdings_data is provided directly, use it
    if holdings_data:
        positions = holdings_data
    elif portfolio_id:
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
                )
                result = await session.execute(stmt)
                db_holdings = result.scalars().all()
                for h in db_holdings:
                    positions.append(
                        {
                            "ticker": h.company.ticker if h.company else "UNKNOWN",
                            "company_name": h.company.name if h.company else "Unknown",
                            "shares": float(h.shares),
                            "average_buy_price": float(h.average_buy_price),
                            "current_price": float(h.current_price) if h.current_price else float(h.average_buy_price),
                        }
                    )
        except Exception as exc:
            logger.error("calculate_portfolio_allocation failed: %s", exc)
            return {"status": "error", "message": f"Database query failed: {str(exc)}"}
    else:
        return {"status": "error", "message": "Either portfolio_id or holdings_data must be supplied."}

    if not positions:
        return {
            "status": "success",
            "total_cost": 0.0,
            "total_market_value": 0.0,
            "unrealized_gain_loss": 0.0,
            "unrealized_gain_loss_pct": 0.0,
            "holdings_count": 0,
            "allocations": [],
            "concentration_metrics": {
                "top_holding_pct": 0.0,
                "hhi_index": 0.0,
                "risk_level": "LOW",
            },
        }

    total_cost_dec = Decimal("0.0000")
    total_market_val_dec = Decimal("0.0000")
    computed_holdings: List[Dict[str, Any]] = []

    for pos in positions:
        shares = Decimal(str(pos.get("shares", 0)))
        buy_price = Decimal(str(pos.get("average_buy_price", 0)))
        curr_price = Decimal(str(pos.get("current_price") or buy_price))

        pos_cost = shares * buy_price
        pos_market_val = shares * curr_price

        total_cost_dec += pos_cost
        total_market_val_dec += pos_market_val

        computed_holdings.append(
            {
                "ticker": pos.get("ticker", "UNKNOWN"),
                "company_name": pos.get("company_name", ""),
                "shares": float(shares),
                "buy_price": float(buy_price),
                "current_price": float(curr_price),
                "cost_basis": float(round(pos_cost, 2)),
                "market_value": float(round(pos_market_val, 2)),
                "_cost_dec": pos_cost,
                "_mv_dec": pos_market_val,
            }
        )

    # Calculate weights and concentration metrics using exact Decimal math
    hhi = Decimal("0.0")
    top_weight = Decimal("0.0")
    for h in computed_holdings:
        mv_dec = h.pop("_mv_dec")
        cost_dec = h.pop("_cost_dec")
        if total_market_val_dec > Decimal("0"):
            weight_pct = (mv_dec / total_market_val_dec) * Decimal("100")
        else:
            weight_pct = Decimal("0.0")

        weight_rounded = round(weight_pct, 2)
        h["weight_pct"] = float(weight_rounded)

        gain_loss = mv_dec - cost_dec
        gain_loss_pct = (gain_loss / cost_dec * Decimal("100")) if cost_dec > Decimal("0") else Decimal("0.0")
        h["unrealized_gain_loss"] = float(round(gain_loss, 2))
        h["unrealized_gain_loss_pct"] = float(round(gain_loss_pct, 2))

        if weight_rounded > top_weight:
            top_weight = weight_rounded
        hhi += weight_rounded ** 2

    # Assess concentration risk based on HHI guidelines (FTC/DOJ thresholds adapted for portfolios)
    top_weight_float = float(top_weight)
    hhi_float = float(hhi)
    if hhi_float > 2500 or top_weight_float > 30.0:
        risk_level = "HIGH"
    elif hhi_float > 1500 or top_weight_float > 20.0:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    unrealized_gl = total_market_val_dec - total_cost_dec
    unrealized_gl_pct = (unrealized_gl / total_cost_dec * Decimal("100")) if total_cost_dec > Decimal("0") else Decimal("0.0")

    return {
        "status": "success",
        "portfolio_id": portfolio_id,
        "holdings_count": len(computed_holdings),
        "total_cost": float(round(total_cost_dec, 2)),
        "total_market_value": float(round(total_market_val_dec, 2)),
        "unrealized_gain_loss": float(round(unrealized_gl, 2)),
        "unrealized_gain_loss_pct": float(round(unrealized_gl_pct, 2)),
        "allocations": sorted(computed_holdings, key=lambda x: x["weight_pct"], reverse=True),
        "concentration_metrics": {
            "top_holding_pct": top_weight_float,
            "hhi_index": round(hhi_float, 1),
            "risk_level": risk_level,
        },
    }


@analysis_mcp.tool(
    name="calculate_company_exposure",
    description="Calculate portfolio exposure and risk concentration for a specific company or ticker.",
)
async def calculate_company_exposure(
    ticker: str,
    portfolio_id: Optional[str] = None,
    holdings_data: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Calculate the absolute and proportional exposure to a target equity."""
    # First get portfolio allocation breakdown
    alloc = await calculate_portfolio_allocation(portfolio_id=portfolio_id, holdings_data=holdings_data)
    if alloc.get("status") != "success":
        return alloc

    clean_ticker = ticker.strip().upper()
    total_val = alloc.get("total_market_value", 0.0)

    matched = [h for h in alloc.get("allocations", []) if h["ticker"].upper() == clean_ticker]
    if not matched:
        return {
            "status": "success",
            "ticker": clean_ticker,
            "has_exposure": False,
            "market_value": 0.0,
            "weight_pct": 0.0,
            "risk_flag": "NO_EXPOSURE",
            "message": f"No active positions held in {clean_ticker}.",
        }

    pos = matched[0]
    weight = pos["weight_pct"]
    val = pos["market_value"]

    if weight >= 25.0:
        flag = "CRITICAL_CONCENTRATION"
    elif weight >= 15.0:
        flag = "HIGH_EXPOSURE"
    elif weight >= 8.0:
        flag = "MODERATE_EXPOSURE"
    else:
        flag = "BALANCED"

    return {
        "status": "success",
        "ticker": clean_ticker,
        "has_exposure": True,
        "shares": pos["shares"],
        "market_value": val,
        "weight_pct": weight,
        "total_portfolio_value": total_val,
        "unrealized_gain_loss": pos["unrealized_gain_loss"],
        "risk_flag": flag,
    }


@analysis_mcp.tool(
    name="detect_duplicate_events",
    description="Check whether a candidate research event already exists via hash check and fuzzy similarity.",
)
async def detect_duplicate_events(
    candidate_title: str,
    candidate_summary: str,
    company_id: Optional[str] = None,
    candidate_event_type: str = "OTHER",
    existing_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate candidate event for duplicates via exact SHA-256 hash or token overlap."""
    clean_title = candidate_title.strip().lower()
    clean_summary = candidate_summary.strip()[:100].lower()

    cid_str = company_id.strip() if company_id else "GENERIC"
    sig = f"{cid_str}:{candidate_event_type.upper()}:{clean_title}:{clean_summary}"
    canonical_hash = hashlib.sha256(sig.encode("utf-8")).hexdigest()

    events_to_compare: List[Dict[str, Any]] = []
    if existing_events is not None:
        events_to_compare = existing_events
    elif company_id:
        try:
            c_uuid = uuid.UUID(company_id.strip())
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(ResearchEvent)
                    .where(ResearchEvent.company_id == c_uuid)
                    .order_by(ResearchEvent.created_at.desc())
                    .limit(20)
                )
                db_events = (await session.execute(stmt)).scalars().all()
                for e in db_events:
                    events_to_compare.append(
                        {
                            "id": str(e.id),
                            "event_hash": e.event_hash,
                            "title": e.title,
                            "summary": e.summary,
                        }
                    )
        except Exception as exc:
            logger.warning("Could not query DB for duplicate check: %s", exc)

    # 1. Exact hash match
    for ev in events_to_compare:
        if ev.get("event_hash") == canonical_hash:
            return {
                "status": "success",
                "is_duplicate": True,
                "confidence": 1.0,
                "canonical_hash": canonical_hash,
                "matched_event_id": ev.get("id"),
                "reason": "Exact deterministic hash collision (identical content).",
            }

    # 2. Fuzzy similarity match
    highest_sim = 0.0
    best_match_id: Optional[str] = None

    for ev in events_to_compare:
        ev_title = ev.get("title", "")
        ev_summary = ev.get("summary", "")

        title_sim = _calculate_text_similarity(candidate_title, ev_title)
        summary_sim = _calculate_text_similarity(candidate_summary, ev_summary)
        combined_sim = (title_sim * 0.4) + (summary_sim * 0.6)

        if combined_sim > highest_sim:
            highest_sim = combined_sim
            best_match_id = ev.get("id")

    if highest_sim >= 0.70:
        return {
            "status": "success",
            "is_duplicate": True,
            "confidence": round(highest_sim, 2),
            "canonical_hash": canonical_hash,
            "matched_event_id": best_match_id,
            "reason": f"High lexical similarity ({int(highest_sim * 100)}%) with prior event.",
        }

    return {
        "status": "success",
        "is_duplicate": False,
        "confidence": round(1.0 - highest_sim, 2),
        "canonical_hash": canonical_hash,
        "matched_event_id": None,
        "reason": "No matching duplicate event found.",
    }


@analysis_mcp.tool(
    name="analyze_company_relationships",
    description="Analyze sector distributions, industry overlaps, and concentration correlations across portfolio holdings.",
)
async def analyze_company_relationships(
    portfolio_id: Optional[str] = None,
    tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Analyze sector exposure and correlate business models across companies in a portfolio."""
    companies_data: List[Dict[str, Any]] = []

    try:
        async with AsyncSessionLocal() as session:
            if portfolio_id:
                p_uuid = uuid.UUID(portfolio_id.strip())
                stmt = (
                    select(Holding)
                    .options(joinedload(Holding.company))
                    .where(Holding.portfolio_id == p_uuid)
                )
                holdings = (await session.execute(stmt)).scalars().all()
                for h in holdings:
                    if h.company:
                        companies_data.append(
                            {
                                "ticker": h.company.ticker,
                                "name": h.company.name,
                                "sector": h.company.sector or "Other",
                                "industry": h.company.industry or "General",
                                "market_value": float(h.market_value) if h.market_value else 0.0,
                            }
                        )
            elif tickers:
                clean_tickers = [t.strip().upper() for t in tickers]
                stmt = select(Company).where(Company.ticker.in_(clean_tickers))
                res_companies = (await session.execute(stmt)).scalars().all()
                for c in res_companies:
                    companies_data.append(
                        {
                            "ticker": c.ticker,
                            "name": c.name,
                            "sector": c.sector or "Other",
                            "industry": c.industry or "General",
                            "market_value": 0.0,
                        }
                    )
    except Exception as exc:
        logger.error("analyze_company_relationships failed: %s", exc)
        return {"status": "error", "message": f"Database query failed: {str(exc)}"}

    if not companies_data:
        return {
            "status": "success",
            "companies_analyzed": 0,
            "sectors": {},
            "industries": {},
            "concentration_risk": "None",
        }

    total_val = sum(c["market_value"] for c in companies_data)
    sector_counts: Dict[str, int] = {}
    sector_values: Dict[str, float] = {}
    industry_counts: Dict[str, int] = {}

    for c in companies_data:
        sec = c["sector"]
        ind = c["industry"]
        val = c["market_value"]

        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        sector_values[sec] = sector_values.get(sec, 0.0) + val
        industry_counts[ind] = industry_counts.get(ind, 0) + 1

    sector_pcts = {
        sec: round((val / total_val * 100), 2) if total_val > 0 else 0.0
        for sec, val in sector_values.items()
    }

    dominant_sector = max(sector_pcts.items(), key=lambda x: x[1]) if sector_pcts else ("None", 0.0)
    risk_level = "HIGH" if dominant_sector[1] > 45.0 else "MODERATE" if dominant_sector[1] > 25.0 else "LOW"

    return {
        "status": "success",
        "companies_analyzed": len(companies_data),
        "sector_breakdown": sector_pcts,
        "sector_holding_counts": sector_counts,
        "industry_counts": industry_counts,
        "dominant_sector": dominant_sector[0],
        "dominant_sector_pct": dominant_sector[1],
        "sector_concentration_risk": risk_level,
    }


if __name__ == "__main__":
    analysis_mcp.run()

