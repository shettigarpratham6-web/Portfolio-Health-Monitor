"""
AgentX – Portfolio Health Monitor
LangGraph Shared State Definition
Defines strongly typed execution state, reducers, phase transition models, and initial state factory.
"""

from datetime import datetime, timezone
from enum import Enum
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from app.agents.discovery_agent import DiscoveredEvent
from app.agents.impact_agent import PortfolioImpactReport
from app.agents.portfolio_agent import PortfolioContext
from app.agents.reporting_agent import MonitoringReport
from app.agents.supervisor import MonitoringRequestType, SupervisorExecutionPlan, SupervisorOutput
from app.agents.verification_agent import VerifiedEvent

DEFAULT_NON_ADVISORY_NOTICE = (
    "Notice: This system provides objective risk and event monitoring only. "
    "It does NOT contain investment recommendations to buy, sell, or hold any financial security."
)


class WorkflowNodeName(str, Enum):
    """Canonical names for all LangGraph nodes."""
    SUPERVISOR = "supervisor"
    PORTFOLIO_INTELLIGENCE = "portfolio_intelligence"
    DISCOVERY = "discovery"
    VERIFICATION = "verification"
    IMPACT = "impact"
    REPORTING = "reporting"
    FINAL_RESULT = "final_result"


class WorkflowStatus(str, Enum):
    """High-level execution status of the graph."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class PhaseExecutionRecord(BaseModel):
    """Immutable audit trail entry for a completed or failed stage."""
    node_name: str
    status: str
    details: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retries_attempted: int = 0


class AgentXState(TypedDict, total=False):
    """
    Strongly typed shared state passed through all nodes in the AgentX LangGraph workflow.
    Uses reducers for appending errors and phase audit records without overwriting.
    """
    # --------------------------------------------------------------------------
    # Request & Configuration
    # --------------------------------------------------------------------------
    portfolio_id: str
    user_id: Optional[str]
    request_type: str
    specific_tickers: Optional[List[str]]
    max_news_per_target: int
    max_filings_per_target: int
    include_filings: bool
    include_news: bool
    persist_alerts: bool
    max_retries: int
    max_iterations: int

    # --------------------------------------------------------------------------
    # Routing, Control Flow & Loop Protection
    # --------------------------------------------------------------------------
    current_node: str
    next_node: Optional[str]
    status: str
    iteration_count: int
    retry_counts: Dict[str, int]
    execution_plan: Optional[SupervisorExecutionPlan]
    phase_history: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]

    # --------------------------------------------------------------------------
    # Agent Stage Artifacts
    # --------------------------------------------------------------------------
    portfolio_context: Optional[PortfolioContext]
    discovered_events: List[DiscoveredEvent]
    discovery_summary: Optional[str]
    verified_events: List[VerifiedEvent]
    duplicates_filtered_count: int
    verification_summary: Optional[str]
    impact_report: Optional[PortfolioImpactReport]
    monitoring_report: Optional[MonitoringReport]
    final_output: Optional[SupervisorOutput]

    # --------------------------------------------------------------------------
    # Provenance & Compliance
    # --------------------------------------------------------------------------
    started_at: str
    completed_at: Optional[str]
    non_advisory_notice: str


def create_initial_state(
    portfolio_id: str,
    user_id: Optional[str] = None,
    request_type: MonitoringRequestType = MonitoringRequestType.FULL_PORTFOLIO_CHECK,
    specific_tickers: Optional[List[str]] = None,
    max_news_per_target: int = 3,
    max_filings_per_target: int = 2,
    include_filings: bool = True,
    include_news: bool = True,
    persist_alerts: bool = True,
    max_retries: int = 2,
    max_iterations: int = 15,
) -> AgentXState:
    """
    Factory creating a clean initial state for LangGraph workflow execution.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "portfolio_id": portfolio_id.strip(),
        "user_id": user_id.strip() if user_id else None,
        "request_type": request_type.value if hasattr(request_type, "value") else str(request_type),
        "specific_tickers": [t.strip().upper() for t in specific_tickers] if specific_tickers else None,
        "max_news_per_target": max(1, min(max_news_per_target, 10)),
        "max_filings_per_target": max(0, min(max_filings_per_target, 5)),
        "include_filings": include_filings,
        "include_news": include_news,
        "persist_alerts": persist_alerts,
        "max_retries": max(0, min(max_retries, 5)),
        "max_iterations": max(5, min(max_iterations, 30)),
        "current_node": WorkflowNodeName.SUPERVISOR.value,
        "next_node": WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
        "status": WorkflowStatus.PENDING.value,
        "iteration_count": 0,
        "retry_counts": {
            WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value: 0,
            WorkflowNodeName.DISCOVERY.value: 0,
            WorkflowNodeName.VERIFICATION.value: 0,
            WorkflowNodeName.IMPACT.value: 0,
            WorkflowNodeName.REPORTING.value: 0,
        },
        "execution_plan": None,
        "phase_history": [],
        "errors": [],
        "portfolio_context": None,
        "discovered_events": [],
        "discovery_summary": None,
        "verified_events": [],
        "duplicates_filtered_count": 0,
        "verification_summary": None,
        "impact_report": None,
        "monitoring_report": None,
        "final_output": None,
        "started_at": now,
        "completed_at": None,
        "non_advisory_notice": DEFAULT_NON_ADVISORY_NOTICE,
    }

