"""
Portfolio Health Monitor – Unit Tests for LangGraph Workflow Orchestration Layer
Tests coverage for:
1. Strongly typed state initialization and reducers
2. Full end-to-end multi-agent orchestration
   (Supervisor -> Portfolio Intelligence -> News Discovery -> Research Verification -> Portfolio Impact -> Alert Reporting -> Final Result)
3. Empty portfolio fast-path routing
4. Invalid user request rejection without looping
5. Maximum iteration limit guard (infinite loop protection)
6. Controlled retry mechanisms on transient failure
7. Graceful degradation when retries are exhausted
8. Checkpointer persistence with thread configuration
9. Checkpointer factory behavior
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List
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
    SupervisorAgent,
    SupervisorExecutionPlan,
    SupervisorInput,
    SupervisorOutput,
    WorkflowPhase,
)
from app.agents.verification_agent import (
    VerificationAgent,
    VerificationAgentInput,
    VerificationOutput,
    VerifiedEvent,
    VerifiedFact,
)
from app.graph.state import (
    DEFAULT_NON_ADVISORY_NOTICE,
    AgentXState,
    WorkflowNodeName,
    WorkflowStatus,
    create_initial_state,
)
from app.graph.workflow import (
    AgentXWorkflow,
    create_agentx_graph,
    get_checkpointer,
)
from langgraph.checkpoint.memory import MemorySaver


# ==============================================================================
# Helper Mock Factories
# ==============================================================================
def create_mock_portfolio_context(portfolio_id: str, empty: bool = False) -> PortfolioContext:
    if empty:
        return PortfolioContext(
            portfolio_id=portfolio_id,
            name="Empty Fund",
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
            summary_analysis="Empty portfolio.",
        )

    return PortfolioContext(
        portfolio_id=portfolio_id,
        name="Tech Titan Fund",
        currency="USD",
        total_cost=10000.0,
        total_market_value=12500.0,
        unrealized_gain_loss=2500.0,
        unrealized_gain_loss_pct=25.0,
        holdings=[
            HoldingContext(
                holding_id="h-msft",
                company_id="c-msft",
                ticker="MSFT",
                company_name="Microsoft Corp.",
                sector="Technology",
                shares=25.0,
                buy_price=400.0,
                current_price=500.0,
                cost_basis=10000.0,
                market_value=12500.0,
                weight_pct=100.0,
                unrealized_gain_loss=2500.0,
                unrealized_gain_loss_pct=25.0,
            )
        ],
        tickers=["MSFT"],
        dominant_sector="Technology",
        dominant_sector_pct=100.0,
        concentration_risk_level="HIGH",
        summary_analysis="Concentrated in MSFT.",
    )


def create_mock_discovery_output() -> DiscoveryOutput:
    return DiscoveryOutput(
        total_discovered=1,
        companies_searched=["MSFT"],
        discovered_events=[
            DiscoveredEvent(
                company_name="Microsoft Corp.",
                ticker="MSFT",
                company_id="c-msft",
                title="Microsoft Expands Azure AI Cloud Capacity",
                url="https://azure.microsoft.com/blog/ai-expansion",
                source_name="Microsoft Official Blog",
                snippet="Significant infrastructure upgrade for enterprise cloud...",
                publication_date="2026-11-06T10:00:00Z",
                event_category="NEWS",
            )
        ],
        discovery_summary="Found 1 enterprise announcement.",
    )


def create_mock_verification_output() -> VerificationOutput:
    return VerificationOutput(
        total_reviewed=1,
        total_verified=1,
        duplicates_filtered=0,
        verified_events=[
            VerifiedEvent(
                company_name="Microsoft Corp.",
                ticker="MSFT",
                company_id="c-msft",
                canonical_title="Microsoft Expands Azure AI Cloud Capacity",
                verified_summary="Verified enterprise AI cloud infrastructure expansion.",
                event_type="PRODUCT",
                sentiment="BULLISH",
                verification_status="VERIFIED",
                credibility_score=0.95,
                primary_source_url="https://azure.microsoft.com/blog/ai-expansion",
                source_name="Microsoft Official Blog",
                published_date="2026-11-06T10:00:00Z",
                event_hash="hash-msft-azure",
                facts=[VerifiedFact(statement="Capacity increased by 30%", confidence=1.0)],
            )
        ],
        verification_summary="1 verified product announcement.",
    )


def create_mock_impact_report(portfolio_id: str) -> PortfolioImpactReport:
    return PortfolioImpactReport(
        portfolio_id=portfolio_id,
        portfolio_name="Tech Titan Fund",
        total_events_evaluated=1,
        direct_impacts_count=1,
        indirect_impacts_count=0,
        aggregate_risk_level="LOW",
        highest_impact_holding="MSFT",
        holding_impacts=[
            HoldingImpact(
                ticker="MSFT",
                company_name="Microsoft Corp.",
                holding_weight_pct=100.0,
                holding_market_value=12500.0,
                direct_exposure=True,
                event_title="Microsoft Expands Azure AI Cloud Capacity",
                event_type="PRODUCT",
                impact_direction="POSITIVE",
                impact_severity="MEDIUM",
                impact_score=5.0,
                weighted_portfolio_risk=25.0,
                deterministic_rationale="Positive cloud expansion on 100% position",
            )
        ],
        impact_summary="Favorable commercial expansion.",
    )


def create_mock_monitoring_report(portfolio_id: str) -> MonitoringReport:
    return MonitoringReport(
        portfolio_id=portfolio_id,
        executive_summary="Monitoring pipeline completed. 1 verified positive development evaluated.",
        aggregate_risk_level="LOW",
        alerts=[
            StructuredAlertItem(
                portfolio_id=portfolio_id,
                ticker="MSFT",
                title="MEDIUM Impact on MSFT: Microsoft Expands Azure AI",
                alert_type="RESEARCH_UPDATE",
                severity="MEDIUM",
                message="Positive Azure expansion.",
                affected_holdings=["MSFT"],
                evidence_sources=["https://azure.microsoft.com/blog/ai-expansion"],
                persisted=True,
            )
        ],
        persisted_alerts_count=1,
        persisted_events_count=1,
    )


# ==============================================================================
# 1. State Initialization & Defaults
# ==============================================================================
def test_create_initial_state():
    """Verify initial state construction, limits clipping, and default values."""
    p_id = str(uuid.uuid4())
    state = create_initial_state(
        portfolio_id=p_id,
        user_id="user-123",
        request_type=MonitoringRequestType.FULL_PORTFOLIO_CHECK,
        max_news_per_target=25,  # Should clip to 10
        max_filings_per_target=-5,  # Should clip to 0
        max_retries=10,  # Should clip to 5
        max_iterations=100,  # Should clip to 30
    )

    assert state["portfolio_id"] == p_id
    assert state["user_id"] == "user-123"
    assert state["request_type"] == "full_portfolio_check"
    assert state["max_news_per_target"] == 10
    assert state["max_filings_per_target"] == 0
    assert state["max_retries"] == 5
    assert state["max_iterations"] == 30
    assert state["status"] == WorkflowStatus.PENDING.value
    assert state["current_node"] == WorkflowNodeName.SUPERVISOR.value
    assert state["iteration_count"] == 0
    assert state["errors"] == []
    assert state["phase_history"] == []
    assert "NOT contain investment recommendations to buy, sell, or hold" in state["non_advisory_notice"]


# ==============================================================================
# 2. End-to-End Successful Workflow Execution
# ==============================================================================
@pytest.mark.asyncio
async def test_graph_full_successful_execution():
    """
    Test complete sequential execution across all graph nodes:
    User request -> Supervisor -> Portfolio Intelligence -> News Discovery ->
    Research Verification -> Portfolio Impact -> Alert Reporting -> Final Result.
    """
    test_p_id = str(uuid.uuid4())

    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_p_agent.run = AsyncMock(return_value=create_mock_portfolio_context(test_p_id))

    mock_d_agent = MagicMock(spec=DiscoveryAgent)
    mock_d_agent.run = AsyncMock(return_value=create_mock_discovery_output())

    mock_v_agent = MagicMock(spec=VerificationAgent)
    mock_v_agent.run = AsyncMock(return_value=create_mock_verification_output())

    mock_i_agent = MagicMock(spec=ImpactAgent)
    mock_i_agent.run = AsyncMock(return_value=create_mock_impact_report(test_p_id))

    mock_r_agent = MagicMock(spec=ReportingAgent)
    mock_r_agent.run = AsyncMock(return_value=create_mock_monitoring_report(test_p_id))

    # Compile workflow with mocked agents
    graph = create_agentx_graph(
        portfolio_agent=mock_p_agent,
        discovery_agent=mock_d_agent,
        verification_agent=mock_v_agent,
        impact_agent=mock_i_agent,
        reporting_agent=mock_r_agent,
    )

    initial_state = create_initial_state(portfolio_id=test_p_id)
    final_state = await graph.ainvoke(initial_state)

    assert final_state["status"] == "SUCCESS"
    assert final_state["portfolio_id"] == test_p_id
    assert final_state["portfolio_context"] is not None
    assert len(final_state["discovered_events"]) == 1
    assert len(final_state["verified_events"]) == 1
    assert final_state["impact_report"] is not None
    assert final_state["monitoring_report"] is not None
    assert len(final_state["errors"]) == 0

    # Verify final_output contract
    out: SupervisorOutput = final_state["final_output"]
    assert out.status == "SUCCESS"
    assert out.portfolio_id == test_p_id
    assert out.monitoring_report.aggregate_risk_level == "LOW"
    assert "NOT contain investment recommendations" in out.non_advisory_notice

    # Verify each agent was called exactly once
    mock_p_agent.run.assert_called_once()
    mock_d_agent.run.assert_called_once()
    mock_v_agent.run.assert_called_once()
    mock_i_agent.run.assert_called_once()
    mock_r_agent.run.assert_called_once()


# ==============================================================================
# 3. Empty Portfolio Fast-Path Routing
# ==============================================================================
@pytest.mark.asyncio
async def test_graph_empty_portfolio_fast_path():
    """
    Test that an empty portfolio routes directly from portfolio intelligence
    to reporting, bypassing discovery, verification, and impact.
    """
    test_p_id = str(uuid.uuid4())

    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_p_agent.run = AsyncMock(return_value=create_mock_portfolio_context(test_p_id, empty=True))

    mock_d_agent = MagicMock(spec=DiscoveryAgent)
    mock_v_agent = MagicMock(spec=VerificationAgent)
    mock_i_agent = MagicMock(spec=ImpactAgent)
    mock_r_agent = MagicMock(spec=ReportingAgent)

    graph = create_agentx_graph(
        portfolio_agent=mock_p_agent,
        discovery_agent=mock_d_agent,
        verification_agent=mock_v_agent,
        impact_agent=mock_i_agent,
        reporting_agent=mock_r_agent,
    )

    initial_state = create_initial_state(portfolio_id=test_p_id)
    final_state = await graph.ainvoke(initial_state)

    assert final_state["status"] == "SUCCESS"
    assert final_state["portfolio_context"].holdings == []
    assert final_state["discovered_events"] == []
    assert final_state["verified_events"] == []
    assert final_state["monitoring_report"] is not None
    assert "no active holdings" in final_state["monitoring_report"].executive_summary.lower()

    # Downstream research agents must NOT be called
    mock_d_agent.run.assert_not_called()
    mock_v_agent.run.assert_not_called()
    mock_i_agent.run.assert_not_called()


# ==============================================================================
# 4. Invalid User Request Handling
# ==============================================================================
@pytest.mark.asyncio
async def test_graph_invalid_request_handling():
    """
    Test that invalid input (empty portfolio_id) is halted by Supervisor
    and cleanly routed to final_result without entering loops.
    """
    mock_p_agent = MagicMock(spec=PortfolioAgent)
    graph = create_agentx_graph(portfolio_agent=mock_p_agent)

    initial_state = create_initial_state(portfolio_id="")
    final_state = await graph.ainvoke(initial_state)

    assert final_state["status"] == "FAILED"
    assert len(final_state["errors"]) >= 1
    assert "portfolio_id is required" in final_state["errors"][0]
    # Downstream agents were never reached
    mock_p_agent.run.assert_not_called()


# ==============================================================================
# 5. Maximum Iteration Limit Guard (Loop Protection)
# ==============================================================================
@pytest.mark.asyncio
async def test_graph_iteration_limit_protection():
    """
    Test that workflow halts if iteration_count exceeds max_iterations,
    preventing infinite loops.
    """
    test_p_id = str(uuid.uuid4())
    mock_p_agent = MagicMock(spec=PortfolioAgent)
    graph = create_agentx_graph(portfolio_agent=mock_p_agent)

    # Set state so that the next iteration exceeds max_iterations
    initial_state = create_initial_state(portfolio_id=test_p_id, max_iterations=5)
    initial_state["iteration_count"] = 5

    final_state = await graph.ainvoke(initial_state)

    assert final_state["status"] == "FAILED"
    assert any("maximum execution iteration limit" in err for err in final_state["errors"])
    mock_p_agent.run.assert_not_called()


# ==============================================================================
# 6. Controlled Retries on Transient Node Failure
# ==============================================================================
@pytest.mark.asyncio
async def test_graph_retry_behavior_on_transient_failure():
    """
    Test that a node retries on transient exception up to max_retries,
    then resumes the workflow successfully.
    """
    test_p_id = str(uuid.uuid4())

    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_p_agent.run = AsyncMock(return_value=create_mock_portfolio_context(test_p_id))

    # Discovery fails on 1st attempt, succeeds on 2nd attempt
    mock_d_agent = MagicMock(spec=DiscoveryAgent)
    mock_d_agent.run = AsyncMock(
        side_effect=[
            ConnectionResetError("Temporary network reset during search"),
            create_mock_discovery_output(),
        ]
    )

    mock_v_agent = MagicMock(spec=VerificationAgent)
    mock_v_agent.run = AsyncMock(return_value=create_mock_verification_output())

    mock_i_agent = MagicMock(spec=ImpactAgent)
    mock_i_agent.run = AsyncMock(return_value=create_mock_impact_report(test_p_id))

    mock_r_agent = MagicMock(spec=ReportingAgent)
    mock_r_agent.run = AsyncMock(return_value=create_mock_monitoring_report(test_p_id))

    graph = create_agentx_graph(
        portfolio_agent=mock_p_agent,
        discovery_agent=mock_d_agent,
        verification_agent=mock_v_agent,
        impact_agent=mock_i_agent,
        reporting_agent=mock_r_agent,
    )

    initial_state = create_initial_state(portfolio_id=test_p_id, max_retries=2)
    final_state = await graph.ainvoke(initial_state)

    # Discovery was called twice (initial + 1 retry)
    assert mock_d_agent.run.call_count == 2
    assert final_state["retry_counts"][WorkflowNodeName.DISCOVERY.value] == 1
    # Downstream agents proceeded to complete
    assert final_state["monitoring_report"] is not None
    # Because an error was encountered during the retry, status reflects PARTIAL_SUCCESS or SUCCESS with errors logged
    assert len(final_state["errors"]) == 1
    assert "Temporary network reset" in final_state["errors"][0]


# ==============================================================================
# 7. Graceful Degradation on Exhausted Retries
# ==============================================================================
@pytest.mark.asyncio
async def test_graph_retries_exhaustion_graceful_degradation():
    """
    Test that when a non-fatal node (discovery) exhausts its retries,
    the workflow degrades gracefully with empty events rather than crashing.
    """
    test_p_id = str(uuid.uuid4())

    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_p_agent.run = AsyncMock(return_value=create_mock_portfolio_context(test_p_id))

    # Discovery fails consistently
    mock_d_agent = MagicMock(spec=DiscoveryAgent)
    mock_d_agent.run = AsyncMock(side_effect=TimeoutError("Tavily search timeout"))

    mock_v_agent = MagicMock(spec=VerificationAgent)
    mock_v_agent.run = AsyncMock(
        return_value=VerificationOutput(
            total_reviewed=0,
            total_verified=0,
            duplicates_filtered=0,
            verified_events=[],
            verification_summary="0 events verified.",
        )
    )

    mock_i_agent = MagicMock(spec=ImpactAgent)
    mock_i_agent.run = AsyncMock(
        return_value=PortfolioImpactReport(
            portfolio_id=test_p_id,
            portfolio_name="Tech Titan Fund",
            total_events_evaluated=0,
            direct_impacts_count=0,
            indirect_impacts_count=0,
            aggregate_risk_level="LOW",
            holding_impacts=[],
            impact_summary="No events to evaluate.",
        )
    )

    mock_r_agent = MagicMock(spec=ReportingAgent)
    mock_r_agent.run = AsyncMock(
        return_value=MonitoringReport(
            portfolio_id=test_p_id,
            executive_summary="Monitoring completed with empty research findings.",
            aggregate_risk_level="LOW",
            alerts=[],
        )
    )

    graph = create_agentx_graph(
        portfolio_agent=mock_p_agent,
        discovery_agent=mock_d_agent,
        verification_agent=mock_v_agent,
        impact_agent=mock_i_agent,
        reporting_agent=mock_r_agent,
    )

    # Set max_retries to 1
    initial_state = create_initial_state(portfolio_id=test_p_id, max_retries=1)
    final_state = await graph.ainvoke(initial_state)

    # Initial attempt + 1 retry = 2 calls
    assert mock_d_agent.run.call_count == 2
    assert final_state["retry_counts"][WorkflowNodeName.DISCOVERY.value] == 2
    assert final_state["status"] == "PARTIAL_SUCCESS"
    assert final_state["discovered_events"] == []
    assert final_state["monitoring_report"] is not None


# ==============================================================================
# 8. Checkpointer Persistence with Thread Configuration
# ==============================================================================
@pytest.mark.asyncio
async def test_graph_checkpointing_and_thread_state():
    """
    Test compiling graph with MemorySaver checkpointer and persisting state across runs.
    """
    test_p_id = str(uuid.uuid4())
    saver = MemorySaver()

    mock_p_agent = MagicMock(spec=PortfolioAgent)
    mock_p_agent.run = AsyncMock(return_value=create_mock_portfolio_context(test_p_id, empty=True))

    graph = create_agentx_graph(
        portfolio_agent=mock_p_agent,
        checkpointer=saver,
    )

    thread_id = f"thread-{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = create_initial_state(portfolio_id=test_p_id)
    final_state = await graph.ainvoke(initial_state, config=config)

    assert final_state["status"] == "SUCCESS"

    # Verify checkpointer saved state under thread_id
    saved_state = await graph.aget_state(config)
    assert saved_state is not None
    assert saved_state.values["portfolio_id"] == test_p_id
    assert saved_state.values["status"] == "SUCCESS"


# ==============================================================================
# 9. Checkpointer Factory Behavior
# ==============================================================================
def test_get_checkpointer_types():
    """Test get_checkpointer returns MemorySaver by default and handles postgres mode."""
    mem_saver = get_checkpointer("memory")
    assert isinstance(mem_saver, MemorySaver)

    # "postgres" mode should gracefully fall back to MemorySaver when langgraph-checkpoint-postgres is absent
    pg_saver = get_checkpointer("postgres", conn_string="postgresql://localhost:5432/test")
    assert isinstance(pg_saver, MemorySaver)

