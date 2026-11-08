"""
AgentX – Unit Tests for Autonomous Monitoring Agents
Tests coverage for:
1. Portfolio Intelligence Agent
2. News & Filing Discovery Agent
3. Research & Verification Agent
4. Portfolio Impact Agent
5. Alert & Reporting Agent
6. Supervisor Agent (Plan formulation, end-to-end delegation, error recovery)
"""

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Dict, List
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.agents.discovery_agent import (
    CompanyTarget,
    DiscoveredEvent,
    DiscoveryAgent,
    DiscoveryAgentInput,
    DiscoveryOutput,
)
from app.agents.impact_agent import (
    HoldingImpact,
    ImpactAgent,
    ImpactAgentInput,
    PortfolioImpactReport,
)
from app.agents.portfolio_agent import (
    HoldingContext,
    PortfolioAgent,
    PortfolioAgentInput,
    PortfolioContext,
)
from app.agents.reporting_agent import (
    MonitoringReport,
    ReportingAgent,
    ReportingAgentInput,
    StructuredAlertItem,
)
from app.agents.supervisor import (
    MonitoringRequestType,
    PhaseStatus,
    SupervisorAgent,
    SupervisorExecutionPlan,
    SupervisorInput,
    SupervisorOutput,
)
from app.agents.verification_agent import (
    LLMVerificationSchema,
    VerificationAgent,
    VerificationAgentInput,
    VerificationOutput,
    VerifiedEvent,
    VerifiedFact,
)
from app.mcp.clients import MCPClient
from app.services.llm import LLMResponse, LLMService


# ==============================================================================
# 1. Portfolio Intelligence Agent Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_portfolio_agent_success():
    """Test Portfolio Intelligence Agent builds normalized context from MCP tools."""
    mock_mcp = MagicMock(spec=MCPClient)
    test_p_id = str(uuid.uuid4())
    test_c_id = str(uuid.uuid4())
    test_h_id = str(uuid.uuid4())

    async def mock_call_tool(tool_name: str, arguments: Dict[str, Any], server_name: str):
        if tool_name == "get_portfolio":
            return {
                "status": "success",
                "portfolio": {
                    "portfolio_id": test_p_id,
                    "name": "Tech Growth Portfolio",
                    "currency": "USD",
                    "description": "Tech heavy portfolio",
                },
            }
        elif tool_name == "get_holdings":
            return {
                "status": "success",
                "holdings": [
                    {
                        "holding_id": test_h_id,
                        "company_id": test_c_id,
                        "ticker": "AAPL",
                        "company_name": "Apple Inc.",
                        "sector": "Technology",
                        "shares": 10.0,
                        "buy_price": 150.0,
                        "current_price": 200.0,
                    }
                ],
            }
        elif tool_name == "calculate_portfolio_allocation":
            return {
                "total_cost": 1500.0,
                "total_market_value": 2000.0,
                "unrealized_gain_loss": 500.0,
                "unrealized_gain_loss_pct": 33.33,
                "allocations": [
                    {
                        "ticker": "AAPL",
                        "company_name": "Apple Inc.",
                        "shares": 10.0,
                        "buy_price": 150.0,
                        "current_price": 200.0,
                        "cost_basis": 1500.0,
                        "market_value": 2000.0,
                        "weight_pct": 100.0,
                        "unrealized_gain_loss": 500.0,
                        "unrealized_gain_loss_pct": 33.33,
                    }
                ],
                "concentration_metrics": {
                    "top_3_concentration_pct": 100.0,
                    "risk_level": "HIGH",
                },
            }
        elif tool_name == "analyze_company_relationships":
            return {
                "dominant_sector": "Technology",
                "dominant_sector_pct": 100.0,
                "is_sector_concentrated": True,
            }
        raise ValueError(f"Unexpected tool: {tool_name}")

    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)
    mock_llm = MagicMock(spec=LLMService)

    agent = PortfolioAgent(llm_service=mock_llm, mcp_client=mock_mcp)
    result = await agent.run(PortfolioAgentInput(portfolio_id=test_p_id))

    assert result.portfolio_id == test_p_id
    assert result.name == "Tech Growth Portfolio"
    assert result.total_cost == 1500.0
    assert result.total_market_value == 2000.0
    assert len(result.holdings) == 1
    assert result.holdings[0].ticker == "AAPL"
    assert result.holdings[0].weight_pct == 100.0
    assert result.dominant_sector == "Technology"
    assert result.concentration_risk_level == "HIGH"


@pytest.mark.asyncio
async def test_portfolio_agent_not_found():
    """Test Portfolio Intelligence Agent raises ValueError on nonexistent portfolio."""
    mock_mcp = MagicMock(spec=MCPClient)
    mock_mcp.call_tool = AsyncMock(return_value={"status": "error", "message": "Portfolio not found"})
    mock_llm = MagicMock(spec=LLMService)

    agent = PortfolioAgent(llm_service=mock_llm, mcp_client=mock_mcp)
    with pytest.raises(ValueError, match="not found"):
        await agent.run(PortfolioAgentInput(portfolio_id=str(uuid.uuid4())))


# ==============================================================================
# 2. News & Filing Discovery Agent Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_discovery_agent_run():
    """Test Discovery Agent queries Research MCP tools and compiles candidate events."""
    mock_mcp = MagicMock(spec=MCPClient)

    async def mock_call_tool(tool_name: str, arguments: Dict[str, Any], server_name: str):
        if tool_name == "search_company_news":
            return {
                "status": "success",
                "articles": [
                    {
                        "title": "Apple Reports Record Services Revenue",
                        "url": "https://example.com/aapl-news",
                        "source_name": "Reuters",
                        "publication_date": "2026-11-01T12:00:00Z",
                        "snippet": "Apple posted strong services earnings...",
                        "score": 0.95,
                    }
                ],
            }
        elif tool_name == "search_company_filings":
            return {
                "status": "success",
                "filings": [
                    {
                        "title": "Apple Inc. Form 10-K Annual Report",
                        "url": "https://sec.gov/edgar/aapl-10k",
                        "source_name": "SEC EDGAR",
                        "publication_date": "2026-10-30T16:00:00Z",
                        "snippet": "Item 1. Business overview...",
                        "score": 0.99,
                    }
                ],
            }
        return {"status": "success"}

    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)
    mock_llm = MagicMock(spec=LLMService)

    agent = DiscoveryAgent(llm_service=mock_llm, mcp_client=mock_mcp)
    input_payload = DiscoveryAgentInput(
        targets=[CompanyTarget(company_name="Apple Inc.", ticker="AAPL", company_id="comp-1")],
        max_news_per_target=2,
        max_filings_per_target=1,
    )
    result = await agent.run(input_payload)

    assert result.total_discovered == 2
    assert any("AAPL" in s for s in result.companies_searched)
    assert len(result.discovered_events) == 2
    categories = {ev.event_category for ev in result.discovered_events}
    assert "NEWS" in categories
    assert "FILING" in categories


# ==============================================================================
# 3. Research & Verification Agent Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_verification_agent_deduplication_and_verification():
    """Test Verification Agent filters duplicates via MCP and classifies facts vs speculation."""
    mock_mcp = MagicMock(spec=MCPClient)

    # First event is unique; second event is flagged as a duplicate by MCP
    async def mock_call_tool(tool_name: str, arguments: Dict[str, Any], server_name: str):
        if tool_name == "detect_duplicate_events":
            title = arguments.get("candidate_title", "")
            if "Duplicate" in title:
                return {
                    "is_duplicate": True,
                    "similarity_score": 0.92,
                    "canonical_hash": "hash-dup-123",
                    "matching_title": "Original Event",
                }
            return {
                "is_duplicate": False,
                "similarity_score": 0.1,
                "canonical_hash": "hash-orig-456",
                "matching_title": None,
            }
        return {}

    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)

    mock_llm = MagicMock(spec=LLMService)
    # Mock OpenRouter structured response as Pydantic instance
    mock_llm.generate_structured = AsyncMock(
        return_value=LLMVerificationSchema(
            canonical_title="Apple Q4 Services Growth Beat Estimates",
            verified_summary="Services revenue grew 12% YoY, surpassing Wall Street expectations.",
            event_type="EARNINGS",
            sentiment="BULLISH",
            verification_status="VERIFIED",
            credibility_score=0.90,
            facts=["Services revenue grew 12% YoY", "Total services reached $25B"],
            speculative_claims=["Analysts speculate new AI features may drive 2027 upgrade cycle"],
        )
    )

    agent = VerificationAgent(llm_service=mock_llm, mcp_client=mock_mcp)
    input_payload = VerificationAgentInput(
        discovered_events=[
            DiscoveredEvent(
                company_name="Apple Inc.",
                ticker="AAPL",
                title="Apple Reports Record Services Revenue",
                url="https://reuters.com/aapl-q4",
                source_name="Reuters",
                snippet="Services revenue grew 12% YoY...",
                publication_date="2026-11-01T10:00:00Z",
            ),
            DiscoveredEvent(
                company_name="Apple Inc.",
                ticker="AAPL",
                title="Duplicate: Apple Services Revenue Hits Record High",
                url="https://bloomberg.com/aapl-q4-dup",
                source_name="Bloomberg",
                snippet="Services hit all time high...",
                publication_date="2026-11-01T10:30:00Z",
            ),
        ]
    )

    output = await agent.run(input_payload)

    assert output.total_reviewed == 2
    assert output.duplicates_filtered == 1
    assert output.total_verified == 1
    v_event = output.verified_events[0]
    assert v_event.sentiment == "BULLISH"
    assert v_event.event_type == "EARNINGS"
    assert len(v_event.facts) == 2
    assert len(v_event.speculative_claims) == 1
    assert "analysts speculate" in v_event.speculative_claims[0].lower()


# ==============================================================================
# 4. Portfolio Impact Agent Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_impact_agent_deterministic_scoring():
    """Test Portfolio Impact Agent computes deterministic direct and indirect exposure without advice."""
    mock_mcp = MagicMock(spec=MCPClient)
    mock_llm = MagicMock(spec=LLMService)

    # Provide a portfolio context with AAPL (30%) and MSFT (70%)
    p_context = PortfolioContext(
        portfolio_id="test-p-id",
        name="Balanced Tech",
        currency="USD",
        total_cost=10000.0,
        total_market_value=12000.0,
        unrealized_gain_loss=2000.0,
        unrealized_gain_loss_pct=20.0,
        holdings=[
            HoldingContext(
                holding_id="h-1",
                company_id="c-1",
                ticker="AAPL",
                company_name="Apple Inc.",
                sector="Technology",
                shares=20.0,
                buy_price=150.0,
                current_price=180.0,
                cost_basis=3000.0,
                market_value=3600.0,
                weight_pct=30.0,
                unrealized_gain_loss=600.0,
                unrealized_gain_loss_pct=20.0,
            ),
            HoldingContext(
                holding_id="h-2",
                company_id="c-2",
                ticker="MSFT",
                company_name="Microsoft Corp.",
                sector="Technology",
                shares=20.0,
                buy_price=350.0,
                current_price=420.0,
                cost_basis=7000.0,
                market_value=8400.0,
                weight_pct=70.0,
                unrealized_gain_loss=1400.0,
                unrealized_gain_loss_pct=20.0,
            ),
        ],
        tickers=["AAPL", "MSFT"],
        dominant_sector="Technology",
        dominant_sector_pct=100.0,
        concentration_risk_level="HIGH",
        summary_analysis="Tech concentrated portfolio",
    )

    # Event directly affecting AAPL
    verified_events = [
        VerifiedEvent(
            company_name="Apple Inc.",
            ticker="AAPL",
            canonical_title="DOJ Files Landmark Antitrust Lawsuit Against Apple",
            verified_summary="DOJ alleges monopolistic practices in smartphone market.",
            event_type="REGULATORY",
            sentiment="BEARISH",
            verification_status="VERIFIED",
            credibility_score=0.95,
            primary_source_url="https://justice.gov/news/apple-antitrust",
            source_name="US Department of Justice",
            published_date="2026-11-05T14:00:00Z",
            event_hash="hash-doj-apple",
            facts=[VerifiedFact(statement="Lawsuit filed in federal district court", confidence=1.0)],
        )
    ]

    agent = ImpactAgent(llm_service=mock_llm, mcp_client=mock_mcp)
    report = await agent.run(ImpactAgentInput(portfolio_context=p_context, verified_events=verified_events))

    assert report.total_events_evaluated == 1
    assert report.direct_impacts_count == 1
    assert report.highest_impact_holding == "AAPL"

    # Find the AAPL impact item
    aapl_impact = next(i for i in report.holding_impacts if i.ticker == "AAPL")
    assert aapl_impact.direct_exposure is True
    assert aapl_impact.impact_direction == "NEGATIVE"
    assert aapl_impact.impact_score < 0  # BEARISH gives negative score
    assert "DOJ" in aapl_impact.event_title

    # Verify strict non-advisory compliance
    assert "NOT contain investment recommendations to buy, sell, or hold" in report.non_advisory_disclaimer


# ==============================================================================
# 5. Alert & Reporting Agent Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_reporting_agent_generation_and_persistence():
    """Test Alert & Reporting Agent synthesizes structured alerts and persists via Database MCP."""
    mock_mcp = MagicMock(spec=MCPClient)
    saved_alerts = []
    saved_sources = []

    async def mock_call_tool(tool_name: str, arguments: Dict[str, Any], server_name: str):
        if tool_name == "save_monitoring_alert":
            alert_id = f"alert-{uuid.uuid4()}"
            saved_alerts.append(arguments)
            return {"alert_id": alert_id, "status": "created"}
        elif tool_name == "save_research_event":
            return {"event_id": f"ev-{uuid.uuid4()}", "status": "created"}
        elif tool_name == "save_evidence_source":
            saved_sources.append(arguments)
            return {"source_id": f"src-{uuid.uuid4()}", "status": "created"}
        return {}

    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)

    mock_llm = MagicMock(spec=LLMService)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            content="Summary: 1 regulatory alert recorded for AAPL. Portfolio overall risk level is MEDIUM.",
            model="anthropic/claude-3.5-sonnet",
        )
    )

    impact_report = PortfolioImpactReport(
        portfolio_id="p-100",
        portfolio_name="Growth",
        total_events_evaluated=1,
        direct_impacts_count=1,
        indirect_impacts_count=0,
        aggregate_risk_level="MEDIUM",
        highest_impact_holding="AAPL",
        holding_impacts=[
            HoldingImpact(
                ticker="AAPL",
                company_name="Apple Inc.",
                holding_weight_pct=40.0,
                holding_market_value=4000.0,
                direct_exposure=True,
                event_title="DOJ Antitrust Filing",
                event_type="REGULATORY",
                impact_direction="NEGATIVE",
                impact_severity="MEDIUM",
                impact_score=-6.0,
                weighted_portfolio_risk=-15.6,
                deterministic_rationale="Regulatory event on 40% position",
            )
        ],
        impact_summary="Regulatory action noted.",
    )

    verified_events = [
        VerifiedEvent(
            company_name="Apple Inc.",
            ticker="AAPL",
            company_id="comp-1",
            canonical_title="DOJ Antitrust Filing",
            verified_summary="DOJ antitrust action initiated.",
            event_type="REGULATORY",
            sentiment="BEARISH",
            verification_status="VERIFIED",
            credibility_score=0.9,
            primary_source_url="https://justice.gov/apple",
            source_name="DOJ",
            published_date="2026-11-05",
            event_hash="hash-1",
        )
    ]

    agent = ReportingAgent(llm_service=mock_llm, mcp_client=mock_mcp)
    report = await agent.run(
        ReportingAgentInput(
            portfolio_id="p-100",
            impact_report=impact_report,
            verified_events=verified_events,
            persist_to_database=True,
        )
    )

    assert report.portfolio_id == "p-100"
    assert report.aggregate_risk_level == "MEDIUM"
    assert len(report.alerts) == 1
    assert report.persisted_alerts_count == 1
    assert report.alerts[0].ticker == "AAPL"
    assert "https://justice.gov/apple" in report.alerts[0].evidence_sources
    assert len(saved_alerts) == 1
    assert len(saved_sources) == 1
    assert "NOT contain investment recommendations to buy, sell, or hold" in report.non_advisory_notice


# ==============================================================================
# 6. Supervisor Agent Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_supervisor_execution_plan_creation():
    """Test Supervisor builds valid execution plan matching request parameters."""
    supervisor = SupervisorAgent()
    req = SupervisorInput(
        portfolio_id="p-test",
        request_type=MonitoringRequestType.SINGLE_STOCK_DRILLDOWN,
        specific_tickers=["AAPL"],
    )
    plan = supervisor.create_execution_plan(req)

    assert plan.portfolio_id == "p-test"
    assert plan.request_type == MonitoringRequestType.SINGLE_STOCK_DRILLDOWN
    assert plan.target_tickers == ["AAPL"]
    assert len(plan.phases) == 5
    assert plan.phases[0].phase_name == "portfolio_intelligence"
    assert plan.phases[4].phase_name == "alert_and_reporting"


@pytest.mark.asyncio
async def test_supervisor_end_to_end_successful_orchestration():
    """Test full sequential delegation across all 5 agents with successful outcome."""
    # Mock sub-agents
    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_d_agent = MagicMock(spec=DiscoveryAgent)
    mock_v_agent = MagicMock(spec=VerificationAgent)
    mock_i_agent = MagicMock(spec=ImpactAgent)
    mock_r_agent = MagicMock(spec=ReportingAgent)

    # 1. Portfolio agent returns holding
    mock_p_agent.run = AsyncMock(
        return_value=PortfolioContext(
            portfolio_id="p-123",
            name="Alpha Portfolio",
            currency="USD",
            total_cost=5000.0,
            total_market_value=6000.0,
            unrealized_gain_loss=1000.0,
            unrealized_gain_loss_pct=20.0,
            holdings=[
                HoldingContext(
                    holding_id="h-1",
                    company_id="c-1",
                    ticker="NVDA",
                    company_name="Nvidia Corp.",
                    sector="Semiconductors",
                    shares=10.0,
                    buy_price=500.0,
                    current_price=600.0,
                    cost_basis=5000.0,
                    market_value=6000.0,
                    weight_pct=100.0,
                    unrealized_gain_loss=1000.0,
                    unrealized_gain_loss_pct=20.0,
                )
            ],
            tickers=["NVDA"],
            dominant_sector="Semiconductors",
            dominant_sector_pct=100.0,
            concentration_risk_level="HIGH",
            summary_analysis="Concentrated in NVDA",
        )
    )

    # 2. Discovery agent returns event
    mock_d_agent.run = AsyncMock(
        return_value=DiscoveryOutput(
            total_discovered=1,
            companies_searched=["NVDA"],
            discovered_events=[
                DiscoveredEvent(
                    company_name="Nvidia Corp.",
                    ticker="NVDA",
                    title="Nvidia Unveils Next-Gen AI Architecture",
                    url="https://nvidia.com/news/next-gen",
                    source_name="Nvidia Press",
                    snippet="New architecture doubles throughput...",
                )
            ],
            discovery_summary="Discovered 1 news item",
        )
    )

    # 3. Verification agent returns verified event
    mock_v_agent.run = AsyncMock(
        return_value=VerificationOutput(
            total_reviewed=1,
            total_verified=1,
            duplicates_filtered=0,
            verified_events=[
                VerifiedEvent(
                    company_name="Nvidia Corp.",
                    ticker="NVDA",
                    canonical_title="Nvidia Unveils Next-Gen AI Architecture",
                    verified_summary="New architecture announced at annual summit.",
                    event_type="PRODUCT",
                    sentiment="BULLISH",
                    verification_status="VERIFIED",
                    credibility_score=0.95,
                    primary_source_url="https://nvidia.com/news/next-gen",
                    source_name="Nvidia Press",
                    published_date="2026-11-07",
                    event_hash="hash-nvda-1",
                    facts=[VerifiedFact(statement="Double throughput demonstrated", confidence=1.0)],
                )
            ],
            verification_summary="1 event verified.",
        )
    )

    # 4. Impact agent returns report
    mock_i_agent.run = AsyncMock(
        return_value=PortfolioImpactReport(
            portfolio_id="p-123",
            portfolio_name="Alpha Portfolio",
            total_events_evaluated=1,
            direct_impacts_count=1,
            indirect_impacts_count=0,
            aggregate_risk_level="LOW",
            highest_impact_holding="NVDA",
            holding_impacts=[
                HoldingImpact(
                    ticker="NVDA",
                    company_name="Nvidia Corp.",
                    holding_weight_pct=100.0,
                    holding_market_value=6000.0,
                    direct_exposure=True,
                    event_title="Nvidia Unveils Next-Gen AI Architecture",
                    event_type="PRODUCT",
                    impact_direction="POSITIVE",
                    impact_severity="MEDIUM",
                    impact_score=4.0,
                    weighted_portfolio_risk=20.0,
                    deterministic_rationale="Positive product launch on 100% position",
                )
            ],
            impact_summary="Favorable product development.",
        )
    )

    # 5. Reporting agent returns report
    mock_r_agent.run = AsyncMock(
        return_value=MonitoringReport(
            portfolio_id="p-123",
            executive_summary="All 5 phases completed. NVDA product announcement evaluated.",
            aggregate_risk_level="LOW",
            alerts=[
                StructuredAlertItem(
                    portfolio_id="p-123",
                    ticker="NVDA",
                    title="Nvidia Unveils Next-Gen AI Architecture",
                    alert_type="PRODUCT",
                    severity="MEDIUM",
                    message="Positive product announcement.",
                    evidence_sources=["https://nvidia.com/news/next-gen"],
                    persisted=True,
                )
            ],
            persisted_alerts_count=1,
            persisted_events_count=1,
        )
    )

    supervisor = SupervisorAgent(
        portfolio_agent=mock_p_agent,
        discovery_agent=mock_d_agent,
        verification_agent=mock_v_agent,
        impact_agent=mock_i_agent,
        reporting_agent=mock_r_agent,
    )

    req = SupervisorInput(portfolio_id="p-123")
    output = await supervisor.run(req)

    assert output.status == "SUCCESS"
    assert output.portfolio_id == "p-123"
    assert output.portfolio_context is not None
    assert output.discovery_output is not None
    assert output.verification_output is not None
    assert output.impact_report is not None
    assert output.monitoring_report is not None
    assert len(output.errors) == 0

    # Ensure all phases are marked COMPLETED
    for phase in output.execution_plan.phases:
        assert phase.status == PhaseStatus.COMPLETED


@pytest.mark.asyncio
async def test_supervisor_empty_portfolio_skips_downstream():
    """Test Supervisor skips downstream research phases when portfolio contains no holdings."""
    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_p_agent.run = AsyncMock(
        return_value=PortfolioContext(
            portfolio_id="p-empty",
            name="Empty Portfolio",
            currency="USD",
            total_cost=0.0,
            total_market_value=0.0,
            unrealized_gain_loss=0.0,
            unrealized_gain_loss_pct=0.0,
            holdings=[],
            tickers=[],
            dominant_sector="None",
            dominant_sector_pct=0.0,
            concentration_risk_level="LOW",
            summary_analysis="Empty portfolio",
        )
    )
    mock_d_agent = MagicMock(spec=DiscoveryAgent)

    supervisor = SupervisorAgent(
        portfolio_agent=mock_p_agent,
        discovery_agent=mock_d_agent,
    )

    req = SupervisorInput(portfolio_id="p-empty")
    output = await supervisor.run(req)

    assert output.status == "SUCCESS"
    assert output.portfolio_context.holdings == []
    # Phase 0 is completed, phases 1-4 are skipped
    assert output.execution_plan.phases[0].status == PhaseStatus.COMPLETED
    for phase in output.execution_plan.phases[1:]:
        assert phase.status == PhaseStatus.SKIPPED
    # Discovery agent was never called
    mock_d_agent.run.assert_not_called()


@pytest.mark.asyncio
async def test_supervisor_phase_failure_resilience():
    """Test Supervisor handles discovery failure gracefully, producing PARTIAL_SUCCESS without crashing."""
    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_p_agent.run = AsyncMock(
        return_value=PortfolioContext(
            portfolio_id="p-resilient",
            name="Resilient Test Portfolio",
            currency="USD",
            total_cost=1000.0,
            total_market_value=1200.0,
            unrealized_gain_loss=200.0,
            unrealized_gain_loss_pct=20.0,
            holdings=[
                HoldingContext(
                    holding_id="h-1",
                    company_id="c-1",
                    ticker="AAPL",
                    company_name="Apple Inc.",
                    shares=10.0,
                    buy_price=100.0,
                    current_price=120.0,
                    cost_basis=1000.0,
                    market_value=1200.0,
                    weight_pct=100.0,
                    unrealized_gain_loss=200.0,
                    unrealized_gain_loss_pct=20.0,
                )
            ],
            tickers=["AAPL"],
            dominant_sector="Technology",
            dominant_sector_pct=100.0,
            concentration_risk_level="HIGH",
            summary_analysis="AAPL portfolio",
        )
    )

    # Discovery agent fails with a network exception
    mock_d_agent = MagicMock(spec=DiscoveryAgent)
    mock_d_agent.run = AsyncMock(side_effect=ConnectionError("Tavily search network timeout"))

    mock_v_agent = MagicMock(spec=VerificationAgent)
    mock_v_agent.run = AsyncMock(
        return_value=VerificationOutput(
            total_reviewed=0,
            total_verified=0,
            duplicates_filtered=0,
            verified_events=[],
            verification_summary="No events to verify.",
        )
    )

    mock_i_agent = MagicMock(spec=ImpactAgent)
    mock_i_agent.run = AsyncMock(
        return_value=PortfolioImpactReport(
            portfolio_id="p-resilient",
            portfolio_name="Resilient Test Portfolio",
            total_events_evaluated=0,
            direct_impacts_count=0,
            indirect_impacts_count=0,
            aggregate_risk_level="LOW",
            holding_impacts=[],
            impact_summary="No events evaluated.",
        )
    )

    mock_r_agent = MagicMock(spec=ReportingAgent)
    mock_r_agent.run = AsyncMock(
        return_value=MonitoringReport(
            portfolio_id="p-resilient",
            executive_summary="Monitoring completed with partial discovery failure.",
            aggregate_risk_level="LOW",
            alerts=[],
        )
    )

    supervisor = SupervisorAgent(
        portfolio_agent=mock_p_agent,
        discovery_agent=mock_d_agent,
        verification_agent=mock_v_agent,
        impact_agent=mock_i_agent,
        reporting_agent=mock_r_agent,
    )

    req = SupervisorInput(portfolio_id="p-resilient")
    output = await supervisor.run(req)

    assert output.status == "PARTIAL_SUCCESS"
    assert len(output.errors) == 1
    assert "Tavily search network timeout" in output.errors[0]
    assert output.execution_plan.phases[1].status == PhaseStatus.FAILED
    assert output.execution_plan.phases[4].status == PhaseStatus.COMPLETED
    assert output.monitoring_report is not None
