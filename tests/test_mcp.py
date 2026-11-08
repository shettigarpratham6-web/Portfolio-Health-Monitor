"""
AgentX – Portfolio Health Monitor
Unit & Integration Tests for MCP Servers and Client Gateway
"""

import asyncio
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.database import AsyncSessionLocal
from app.mcp.clients import MCPClient, get_langchain_tools, get_mcp_client
from app.mcp.servers.analysis_server import analysis_mcp
from app.mcp.servers.database_server import database_mcp
from app.mcp.servers.research_server import research_mcp
from app.models import Company, Holding, Portfolio, User


# ------------------------------------------------------------------------------
# Test 1: Tool Registration on Server Instances
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_server_tool_registrations():
    r_tools = await research_mcp.list_tools()
    d_tools = await database_mcp.list_tools()
    a_tools = await analysis_mcp.list_tools()

    r_names = {t.name for t in r_tools}
    d_names = {t.name for t in d_tools}
    a_names = {t.name for t in a_tools}

    # Verify Research MCP tools
    assert r_names == {
        "search_company_news",
        "search_company_filings",
        "fetch_webpage",
        "extract_article_content",
    }

    # Verify Database MCP tools
    assert d_names == {
        "get_portfolio",
        "get_holdings",
        "save_research_event",
        "save_evidence_source",
        "save_monitoring_alert",
        "get_previous_alerts",
    }

    # Verify Analysis MCP tools
    assert a_names == {
        "calculate_portfolio_allocation",
        "calculate_company_exposure",
        "detect_duplicate_events",
        "analyze_company_relationships",
    }


# ------------------------------------------------------------------------------
# Test 2: MCP Client Discovery & Catalog
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_mcp_client_discovery():
    client = MCPClient()
    catalog = await client.list_tools()

    assert "research" in catalog
    assert "database" in catalog
    assert "analysis" in catalog

    assert len(catalog["research"]) == 4
    assert len(catalog["database"]) == 6
    assert len(catalog["analysis"]) == 4


# ------------------------------------------------------------------------------
# Test 3: Research MCP Tool Execution via Client
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_research_mcp_tools():
    client = MCPClient()

    # 1. extract_article_content
    html_sample = (
        "<html><head><title>Test Headline</title></head>"
        "<body><article><p>Apple delivered strong financial results for Q4.</p></article></body></html>"
    )
    res_extract = await client.call_tool(
        tool_name="extract_article_content",
        arguments={"html": html_sample, "url": "https://reuters.com/apple-q4"},
    )
    assert res_extract["status"] == "success"
    assert res_extract["article"]["title"] == "Test Headline"
    assert "Apple delivered strong financial results" in res_extract["article"]["extracted_content"]

    # 2. fetch_webpage SSRF protection
    res_fetch_unsafe = await client.call_tool(
        tool_name="fetch_webpage",
        arguments={"url": "http://127.0.0.1:8000/internal"},
    )
    assert res_fetch_unsafe["status"] == "error"
    assert res_fetch_unsafe["error_type"] == "security_restriction"


# ------------------------------------------------------------------------------
# Test 4: Database MCP Tool Execution via Client
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_database_mcp_tools():
    client = MCPClient()

    # 1. get_portfolio validation on bad UUID
    res_bad_uuid = await client.call_tool(
        tool_name="get_portfolio",
        arguments={"portfolio_id": "not-a-valid-uuid"},
    )
    assert res_bad_uuid["status"] == "error"

    # Setup database records for testing
    async with AsyncSessionLocal() as session:
        user = User(
            email=f"mcp_user_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=get_password_hash("pass"),
            full_name="MCP Tester",
        )
        session.add(user)
        await session.flush()

        portfolio = Portfolio(
            user_id=user.id,
            name=f"MCP Growth {uuid.uuid4().hex[:4]}",
            currency="USD",
        )
        company = Company(
            ticker=f"NVDA_{uuid.uuid4().hex[:4]}",
            name="Nvidia Corp",
            sector="Technology",
            industry="Semiconductors",
        )
        session.add_all([portfolio, company])
        await session.flush()

        holding = Holding(
            portfolio_id=portfolio.id,
            company_id=company.id,
            shares=Decimal("100.000000"),
            average_buy_price=Decimal("120.0000"),
            current_price=Decimal("140.0000"),
            market_value=Decimal("14000.0000"),
        )
        session.add(holding)
        await session.commit()

        p_id = str(portfolio.id)
        c_id = str(company.id)

    # 2. get_portfolio valid
    res_p = await client.call_tool(
        tool_name="get_portfolio",
        arguments={"portfolio_id": p_id},
    )
    assert res_p["status"] == "success"
    assert res_p["portfolio"]["id"] == p_id
    assert res_p["portfolio"]["holdings_count"] == 1

    # 3. get_holdings
    res_h = await client.call_tool(
        tool_name="get_holdings",
        arguments={"portfolio_id": p_id},
    )
    assert res_h["status"] == "success"
    assert res_h["count"] == 1
    assert res_h["holdings"][0]["ticker"] == company.ticker

    # 4. save_research_event and deduplication
    res_save_ev = await client.call_tool(
        tool_name="save_research_event",
        arguments={
            "company_id": c_id,
            "title": "Blackwell Chip Shipments Accelerate",
            "summary": "Customer demand for Blackwell architecture exceeds initial estimates.",
            "event_type": "PRODUCT",
            "severity": "HIGH",
            "sentiment": "BULLISH",
            "impact_score": 8.5,
        },
    )
    assert res_save_ev["status"] == "created"
    ev_id = res_save_ev["event_id"]

    # Repeated insertion must be recognized as duplicate
    res_dup_ev = await client.call_tool(
        tool_name="save_research_event",
        arguments={
            "company_id": c_id,
            "title": "Blackwell Chip Shipments Accelerate",
            "summary": "Customer demand for Blackwell architecture exceeds initial estimates.",
            "event_type": "PRODUCT",
        },
    )
    assert res_dup_ev["status"] == "duplicate"
    assert res_dup_ev["event_id"] == ev_id

    # 5. save_evidence_source
    res_source = await client.call_tool(
        tool_name="save_evidence_source",
        arguments={
            "research_event_id": ev_id,
            "source_name": "SEC Form 8-K",
            "source_url": f"https://sec.gov/filing/{uuid.uuid4().hex[:6]}",
            "credibility_score": 0.95,
        },
    )
    assert res_source["status"] == "created"

    # 6. save_monitoring_alert & get_previous_alerts
    res_alert = await client.call_tool(
        tool_name="save_monitoring_alert",
        arguments={
            "portfolio_id": p_id,
            "company_id": c_id,
            "research_event_id": ev_id,
            "title": "Positive Catalyst Detected",
            "message": "Nvidia Blackwell demand confirmed by official filing.",
            "severity": "HIGH",
            "alert_type": "RESEARCH_UPDATE",
        },
    )
    assert res_alert["status"] == "created"

    res_prev_alerts = await client.call_tool(
        tool_name="get_previous_alerts",
        arguments={"portfolio_id": p_id},
    )
    assert res_prev_alerts["status"] == "success"
    assert res_prev_alerts["count"] >= 1
    assert res_prev_alerts["alerts"][0]["title"] == "Positive Catalyst Detected"


# ------------------------------------------------------------------------------
# Test 5: Analysis MCP Tool Execution via Client
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_analysis_mcp_tools():
    client = MCPClient()

    sample_holdings = [
        {"ticker": "AAPL", "shares": 100, "average_buy_price": 150.0, "current_price": 200.0},
        {"ticker": "MSFT", "shares": 50, "average_buy_price": 300.0, "current_price": 400.0},
        {"ticker": "NVDA", "shares": 40, "average_buy_price": 100.0, "current_price": 125.0},
    ]

    # 1. calculate_portfolio_allocation
    res_alloc = await client.call_tool(
        tool_name="calculate_portfolio_allocation",
        arguments={"holdings_data": sample_holdings},
    )
    assert res_alloc["status"] == "success"
    assert res_alloc["total_cost"] == 34000.0  # 15000 + 15000 + 4000
    assert res_alloc["total_market_value"] == 45000.0  # 20000 + 20000 + 5000
    assert res_alloc["unrealized_gain_loss"] == 11000.0
    assert len(res_alloc["allocations"]) == 3
    assert res_alloc["concentration_metrics"]["risk_level"] in ("LOW", "MODERATE", "HIGH")

    # 2. calculate_company_exposure
    res_exp = await client.call_tool(
        tool_name="calculate_company_exposure",
        arguments={"ticker": "AAPL", "holdings_data": sample_holdings},
    )
    assert res_exp["status"] == "success"
    assert res_exp["has_exposure"] is True
    assert res_exp["market_value"] == 20000.0
    assert res_exp["weight_pct"] == 44.44

    # 3. detect_duplicate_events
    existing = [
        {
            "id": "mock-event-1",
            "title": "Nvidia Reports Record Data Center Revenue",
            "summary": "Revenue increased by 112 percent driven by generative AI computing demand.",
            "event_hash": "existing_hash_123",
        }
    ]
    # Paraphrased duplicate candidate
    res_dup = await client.call_tool(
        tool_name="detect_duplicate_events",
        arguments={
            "candidate_title": "Nvidia Reports Record Data Center Revenue",
            "candidate_summary": "Revenue increased driven by generative AI computing demand.",
            "existing_events": existing,
        },
    )
    assert res_dup["status"] == "success"
    assert res_dup["is_duplicate"] is True
    assert res_dup["matched_event_id"] == "mock-event-1"

    # Distinct non-duplicate candidate
    res_distinct = await client.call_tool(
        tool_name="detect_duplicate_events",
        arguments={
            "candidate_title": "FDA Approves New Medical Device",
            "candidate_summary": "Healthcare regulatory agency greenlights cardiac monitoring tool.",
            "existing_events": existing,
        },
    )
    assert res_distinct["status"] == "success"
    assert res_distinct["is_duplicate"] is False


# ------------------------------------------------------------------------------
# Test 6: LangChain Tools Export for LangGraph
# ------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_langchain_tools_export():
    lc_tools = await get_langchain_tools()
    assert len(lc_tools) == 14

    tool_names = {t.name for t in lc_tools}
    assert "search_company_news" in tool_names
    assert "get_portfolio" in tool_names
    assert "calculate_portfolio_allocation" in tool_names

    # Test executing a LangChain StructuredTool directly
    alloc_tool = next(t for t in lc_tools if t.name == "calculate_portfolio_allocation")
    result = await alloc_tool.ainvoke(
        {
            "holdings_data": [
                {"ticker": "AAPL", "shares": 10, "average_buy_price": 100.0, "current_price": 150.0}
            ]
        }
    )
    assert result["status"] == "success"
    assert result["total_market_value"] == 1500.0

