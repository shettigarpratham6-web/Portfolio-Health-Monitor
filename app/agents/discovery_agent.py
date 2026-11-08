"""
AgentX – Portfolio Health Monitor
News & Filing Discovery Agent
Discovers market events, filings, and regulatory disclosures using Research MCP tools.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from langsmith import traceable
from pydantic import BaseModel, Field

from app.mcp.clients import get_mcp_client
from app.services.llm import get_llm_service

logger = logging.getLogger("agentx.agents.discovery")


# ------------------------------------------------------------------------------
# Input & Output Schemas
# ------------------------------------------------------------------------------
class CompanyTarget(BaseModel):
    """Company identification target for discovery."""
    company_name: str
    ticker: str
    company_id: Optional[str] = None


class DiscoveryAgentInput(BaseModel):
    """Input payload for News & Filing Discovery Agent."""
    targets: List[CompanyTarget] = Field(..., description="List of companies/tickers to research")
    max_news_per_target: int = Field(default=3, ge=1, le=10)
    max_filings_per_target: int = Field(default=2, ge=0, le=5)
    include_filings: bool = True
    include_news: bool = True


class DiscoveredEvent(BaseModel):
    """Raw discovered market event or disclosure with preserved provenance."""
    company_name: str
    ticker: str
    company_id: Optional[str] = None
    title: str
    url: str
    source_name: str
    publication_date: Optional[str] = None
    snippet: str = ""
    event_category: str = "NEWS"  # NEWS or FILING
    relevance_score: Optional[float] = None
    discovered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DiscoveryOutput(BaseModel):
    """Aggregated discovery output across all target equities."""
    total_discovered: int
    companies_searched: List[str]
    discovered_events: List[DiscoveredEvent]
    discovery_summary: str


# ------------------------------------------------------------------------------
# Discovery Agent
# ------------------------------------------------------------------------------
class DiscoveryAgent:
    """
    News & Filing Discovery Agent.
    Orchestrates targeted queries against Research MCP servers to collect
    fresh market intelligence, SEC filings, and corporate press releases.
    """

    def __init__(self, mcp_client=None, llm_service=None) -> None:
        self.mcp = mcp_client or get_mcp_client()
        self.llm = llm_service or get_llm_service()

    @traceable(name="News & Filing Discovery Agent", run_type="chain")
    async def run(self, input_data: DiscoveryAgentInput) -> DiscoveryOutput:
        """
        Execute discovery across target companies.
        Collects news and corporate filings while preserving source URLs and metadata.
        """
        targets = input_data.targets
        logger.info("Executing Discovery Agent across %d target companies", len(targets))

        all_events: List[DiscoveredEvent] = []
        companies_searched: List[str] = []

        for target in targets:
            c_name = target.company_name
            ticker = target.ticker.upper()
            companies_searched.append(f"{c_name} ({ticker})")

            # 1. Search news via Research MCP
            if input_data.include_news:
                try:
                    news_res = await self.mcp.call_tool(
                        tool_name="search_company_news",
                        arguments={
                            "company_name": c_name,
                            "ticker": ticker,
                            "max_results": input_data.max_news_per_target,
                        },
                        server_name="research",
                    )
                    articles = news_res.get("articles", []) if news_res.get("status") == "success" else []
                    for art in articles:
                        all_events.append(
                            DiscoveredEvent(
                                company_name=c_name,
                                ticker=ticker,
                                company_id=target.company_id,
                                title=art.get("title", "Untitled News"),
                                url=art.get("url", ""),
                                source_name=art.get("source_name", "news"),
                                publication_date=art.get("publication_date"),
                                snippet=art.get("snippet") or art.get("extracted_content", "")[:300],
                                event_category="NEWS",
                                relevance_score=art.get("score"),
                            )
                        )
                except Exception as exc:
                    logger.warning("News discovery failed for %s (%s): %s", c_name, ticker, exc)

            # 2. Search corporate filings & press releases via Research MCP
            if input_data.include_filings:
                try:
                    filings_res = await self.mcp.call_tool(
                        tool_name="search_company_filings",
                        arguments={
                            "company_name": c_name,
                            "ticker": ticker,
                            "max_results": input_data.max_filings_per_target,
                        },
                        server_name="research",
                    )
                    filings = filings_res.get("filings", []) if filings_res.get("status") == "success" else []
                    for f in filings:
                        all_events.append(
                            DiscoveredEvent(
                                company_name=c_name,
                                ticker=ticker,
                                company_id=target.company_id,
                                title=f.get("title", "Corporate Filing"),
                                url=f.get("url", ""),
                                source_name=f.get("source_name", "sec.gov"),
                                publication_date=f.get("publication_date"),
                                snippet=f.get("snippet") or f.get("extracted_content", "")[:300],
                                event_category="FILING",
                                relevance_score=f.get("score"),
                            )
                        )
                except Exception as exc:
                    logger.warning("Filing discovery failed for %s (%s): %s", c_name, ticker, exc)

        summary = (
            f"Discovery agent retrieved {len(all_events)} items across "
            f"{len(companies_searched)} holdings ({', '.join(companies_searched[:4])})."
        )

        return DiscoveryOutput(
            total_discovered=len(all_events),
            companies_searched=companies_searched,
            discovered_events=all_events,
            discovery_summary=summary,
        )

