"""
AgentX – Portfolio Health Monitor
Portfolio Intelligence Agent
Retrieves holdings, calculates allocation and concentration metrics, and builds portfolio context.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
import uuid

from langsmith import traceable
from pydantic import BaseModel, Field

from app.mcp.clients import get_mcp_client
from app.services.llm import get_llm_service

logger = logging.getLogger("agentx.agents.portfolio")


# ------------------------------------------------------------------------------
# Input & Output Schemas
# ------------------------------------------------------------------------------
class PortfolioAgentInput(BaseModel):
    """Input payload for Portfolio Intelligence Agent."""
    portfolio_id: str = Field(..., description="Target portfolio UUID string")


class HoldingContext(BaseModel):
    """Normalized holding representation enriched with performance and allocation metrics."""
    holding_id: str
    company_id: str
    ticker: str
    company_name: str
    sector: str = "Unknown"
    shares: float
    buy_price: float
    current_price: float
    cost_basis: float
    market_value: float
    weight_pct: float
    unrealized_gain_loss: float
    unrealized_gain_loss_pct: float


class PortfolioContext(BaseModel):
    """Structured portfolio intelligence context passed to downstream agents."""
    portfolio_id: str
    name: str
    currency: str = "USD"
    total_cost: float
    total_market_value: float
    unrealized_gain_loss: float
    unrealized_gain_loss_pct: float
    holdings: List[HoldingContext] = Field(default_factory=list)
    tickers: List[str] = Field(default_factory=list)
    dominant_sector: str = "None"
    dominant_sector_pct: float = 0.0
    concentration_risk_level: str = "LOW"  # LOW, MODERATE, HIGH
    summary_analysis: str = ""


# ------------------------------------------------------------------------------
# Portfolio Intelligence Agent
# ------------------------------------------------------------------------------
class PortfolioAgent:
    """
    Portfolio Intelligence Agent.
    Interacts with Database and Analysis MCP servers to assemble
    a verified structural representation of the user's investment portfolio.
    """

    def __init__(self, mcp_client=None, llm_service=None) -> None:
        self.mcp = mcp_client or get_mcp_client()
        self.llm = llm_service or get_llm_service()

    @traceable(name="Portfolio Intelligence Agent", run_type="chain")
    async def run(self, input_data: PortfolioAgentInput) -> PortfolioContext:
        """
        Execute portfolio intelligence workflow.
        1. Queries portfolio metadata via Database MCP.
        2. Queries active holdings via Database MCP.
        3. Calculates allocations and HHI concentration via Analysis MCP.
        4. Analyzes sector distributions via Analysis MCP.
        5. Synthesizes a structured portfolio context.
        """
        portfolio_id = input_data.portfolio_id.strip()
        logger.info("Executing Portfolio Intelligence Agent for portfolio: %s", portfolio_id)

        # 1. Fetch portfolio metadata
        p_res = await self.mcp.call_tool(
            tool_name="get_portfolio",
            arguments={"portfolio_id": portfolio_id},
            server_name="database",
        )
        if not p_res or p_res.get("status") != "success":
            err_msg = p_res.get("message") if p_res else "Portfolio not found"
            raise ValueError(f"Failed to retrieve portfolio '{portfolio_id}': {err_msg}")

        p_info = p_res.get("portfolio", {})

        # 2. Fetch holdings
        h_res = await self.mcp.call_tool(
            tool_name="get_holdings",
            arguments={"portfolio_id": portfolio_id},
            server_name="database",
        )
        raw_holdings = h_res.get("holdings", []) if h_res.get("status") == "success" else []

        # 3. Calculate allocation and concentration metrics
        alloc_res = await self.mcp.call_tool(
            tool_name="calculate_portfolio_allocation",
            arguments={"portfolio_id": portfolio_id},
            server_name="analysis",
        )

        allocations = alloc_res.get("allocations", [])
        conc_metrics = alloc_res.get("concentration_metrics", {})
        total_cost = float(alloc_res.get("total_cost", 0.0))
        total_market_val = float(alloc_res.get("total_market_value", 0.0))
        unrealized_gl = float(alloc_res.get("unrealized_gain_loss", 0.0))
        unrealized_gl_pct = float(alloc_res.get("unrealized_gain_loss_pct", 0.0))

        # 4. Analyze sector relationships
        sec_res = await self.mcp.call_tool(
            tool_name="analyze_company_relationships",
            arguments={"portfolio_id": portfolio_id},
            server_name="analysis",
        )
        dominant_sec = sec_res.get("dominant_sector", "None")
        dominant_sec_pct = float(sec_res.get("dominant_sector_pct", 0.0))
        conc_risk = conc_metrics.get("risk_level", "LOW")

        # Map holdings into normalized HoldingContext
        holding_contexts: List[HoldingContext] = []
        tickers: List[str] = []

        # Index raw holdings by ticker for company_id and holding_id lookups
        raw_map = {h.get("ticker", "").upper(): h for h in raw_holdings}

        for item in allocations:
            ticker = item.get("ticker", "UNKNOWN").upper()
            tickers.append(ticker)
            raw_meta = raw_map.get(ticker, {})

            holding_contexts.append(
                HoldingContext(
                    holding_id=raw_meta.get("holding_id", str(uuid.uuid4())),
                    company_id=raw_meta.get("company_id", str(uuid.uuid4())),
                    ticker=ticker,
                    company_name=item.get("company_name") or raw_meta.get("company_name", ticker),
                    sector=raw_meta.get("sector") or "Unknown",
                    shares=float(item.get("shares", 0.0)),
                    buy_price=float(item.get("buy_price", 0.0)),
                    current_price=float(item.get("current_price", 0.0)),
                    cost_basis=float(item.get("cost_basis", 0.0)),
                    market_value=float(item.get("market_value", 0.0)),
                    weight_pct=float(item.get("weight_pct", 0.0)),
                    unrealized_gain_loss=float(item.get("unrealized_gain_loss", 0.0)),
                    unrealized_gain_loss_pct=float(item.get("unrealized_gain_loss_pct", 0.0)),
                )
            )

        # 5. Brief summary synthesis
        summary = (
            f"Portfolio '{p_info.get('name')}' holds {len(holding_contexts)} positions "
            f"with total valuation of ${total_market_val:,.2f} ({p_info.get('currency', 'USD')}). "
            f"Unrealized return: {unrealized_gl_pct:+.2f}%. "
            f"Dominant sector: {dominant_sec} ({dominant_sec_pct:.1f}%). "
            f"Concentration risk rating: {conc_risk}."
        )

        return PortfolioContext(
            portfolio_id=portfolio_id,
            name=p_info.get("name", "Unnamed Portfolio"),
            currency=p_info.get("currency", "USD"),
            total_cost=total_cost,
            total_market_value=total_market_val,
            unrealized_gain_loss=unrealized_gl,
            unrealized_gain_loss_pct=unrealized_gl_pct,
            holdings=holding_contexts,
            tickers=tickers,
            dominant_sector=dominant_sec,
            dominant_sector_pct=dominant_sec_pct,
            concentration_risk_level=conc_risk,
            summary_analysis=summary,
        )
