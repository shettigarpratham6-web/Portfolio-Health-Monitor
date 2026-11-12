"""
Portfolio Health Monitor
Research MCP Server
Exposes Web Research, Corporate Announcement & Document Extraction Tools via MCP
"""

import json
import logging
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.services.research import (
    ResearchArticle,
    extract_domain,
    extract_publication_date,
    extract_readable_content,
    get_research_service,
    is_safe_url,
    normalize_url,
)

logger = logging.getLogger("agentx.mcp.research")

# ------------------------------------------------------------------------------
# Server Initialization
# ------------------------------------------------------------------------------
research_mcp = FastMCP(
    name="agentx-research",
    instructions=(
        "AgentX Research MCP Server: Provides tools to search company news, corporate filings, "
        "and fetch and sanitize untrusted external financial web pages."
    ),
)


# ------------------------------------------------------------------------------
# Input Schemas for Tools
# ------------------------------------------------------------------------------
class SearchNewsInput(BaseModel):
    company_name: str = Field(..., description="Target company name (e.g., 'Apple Inc.', 'Nvidia')")
    ticker: Optional[str] = Field(default=None, description="Stock ticker symbol (e.g., 'AAPL', 'NVDA')")
    max_results: int = Field(default=5, ge=1, le=15, description="Maximum news articles to return")


class SearchFilingsInput(BaseModel):
    company_name: str = Field(..., description="Company name for regulatory or press release searches")
    ticker: Optional[str] = Field(default=None, description="Stock ticker symbol")
    max_results: int = Field(default=5, ge=1, le=15, description="Maximum filings/announcements to return")


class FetchWebpageInput(BaseModel):
    url: str = Field(..., description="HTTP or HTTPS URL to retrieve")
    timeout_seconds: float = Field(default=12.0, ge=1.0, le=30.0, description="Request timeout in seconds")


class ExtractArticleInput(BaseModel):
    html: str = Field(..., description="Raw HTML string to parse and sanitize")
    url: str = Field(..., description="Source URL for domain attribution and canonicalization")
    fallback_title: Optional[str] = Field(default=None, description="Optional title if omitted from HTML")


# ------------------------------------------------------------------------------
# Tool Implementations
# ------------------------------------------------------------------------------
@research_mcp.tool(
    name="search_company_news",
    description="Search real-time financial and market news for a company or ticker symbol.",
)
async def search_company_news(
    company_name: str,
    ticker: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Search for verified recent market news regarding a given company or equity."""
    try:
        service = get_research_service()
        articles = await service.search_company_news(
            company_name=company_name,
            ticker=ticker,
            max_results=max_results,
        )
        return {
            "status": "success",
            "company": company_name,
            "ticker": ticker,
            "count": len(articles),
            "articles": [art.model_dump(mode="json") for art in articles],
        }
    except Exception as exc:
        logger.error("search_company_news failed for '%s': %s", company_name, exc)
        return {
            "status": "error",
            "message": f"Failed to search news for {company_name}: {str(exc)}",
            "articles": [],
        }


@research_mcp.tool(
    name="search_company_filings",
    description="Search for official corporate disclosures, SEC filings (8-K, 10-Q), and press releases.",
)
async def search_company_filings(
    company_name: str,
    ticker: Optional[str] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """Search for official regulatory announcements, SEC filings, and corporate press releases."""
    try:
        service = get_research_service()
        filings = await service.search_company_announcements(
            company_name=company_name,
            ticker=ticker,
            max_results=max_results,
        )
        return {
            "status": "success",
            "company": company_name,
            "ticker": ticker,
            "count": len(filings),
            "filings": [f.model_dump(mode="json") for f in filings],
        }
    except Exception as exc:
        logger.error("search_company_filings failed for '%s': %s", company_name, exc)
        return {
            "status": "error",
            "message": f"Failed to search filings for {company_name}: {str(exc)}",
            "filings": [],
        }


@research_mcp.tool(
    name="fetch_webpage",
    description="Safely fetch webpage content over HTTP/HTTPS with paywall detection and SSRF protection.",
)
async def fetch_webpage(
    url: str,
    timeout_seconds: float = 12.0,
) -> Dict[str, Any]:
    """Retrieve raw HTML from an external webpage, respecting paywalls and network boundaries."""
    try:
        if not is_safe_url(url):
            return {
                "status": "error",
                "error_type": "security_restriction",
                "message": f"URL '{url}' is invalid or restricted (SSRF prevention).",
            }

        service = get_research_service()
        html = await service.fetch_webpage(url, timeout=timeout_seconds)
        if html is None:
            return {
                "status": "error",
                "error_type": "fetch_failed",
                "message": f"Could not retrieve content from '{url}' (paywall, 404, or network timeout).",
            }

        return {
            "status": "success",
            "url": normalize_url(url),
            "domain": extract_domain(url),
            "html": html,
            "length": len(html),
        }
    except Exception as exc:
        logger.error("fetch_webpage failed for '%s': %s", url, exc)
        return {
            "status": "error",
            "error_type": "unexpected_error",
            "message": f"Webpage retrieval failed: {str(exc)}",
        }


@research_mcp.tool(
    name="extract_article_content",
    description="Extract sanitized, readable plain text and publication metadata from raw HTML.",
)
def extract_article_content(
    html: str,
    url: str,
    fallback_title: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse raw HTML, strip dangerous scripts and styles, and extract article body and dates."""
    try:
        service = get_research_service()
        article = service.extract_article_from_html(
            html=html,
            url=url,
            fallback_title=fallback_title,
        )
        if not article:
            return {
                "status": "error",
                "message": "No meaningful article content could be extracted from provided HTML.",
            }

        return {
            "status": "success",
            "article": article.model_dump(mode="json"),
        }
    except Exception as exc:
        logger.error("extract_article_content failed for '%s': %s", url, exc)
        return {
            "status": "error",
            "message": f"HTML extraction failed: {str(exc)}",
        }


if __name__ == "__main__":
    # Standard entry point when invoked as a standalone MCP server process
    research_mcp.run()

