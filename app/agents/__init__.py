"""
AgentX – Portfolio Health Monitor
Agents Module
Exports all six specialized monitoring agents and their core input/output schemas:
1. Supervisor Agent
2. Portfolio Intelligence Agent
3. News & Filing Discovery Agent
4. Research & Verification Agent
5. Portfolio Impact Agent
6. Alert & Reporting Agent
"""

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
    WorkflowPhase,
)
from app.agents.verification_agent import (
    VerificationAgent,
    VerificationAgentInput,
    VerificationOutput,
    VerifiedEvent,
    VerifiedFact,
)

__all__ = [
    # Supervisor
    "SupervisorAgent",
    "SupervisorInput",
    "SupervisorOutput",
    "SupervisorExecutionPlan",
    "WorkflowPhase",
    "MonitoringRequestType",
    "PhaseStatus",
    # Portfolio Intelligence
    "PortfolioAgent",
    "PortfolioAgentInput",
    "PortfolioContext",
    "HoldingContext",
    # News & Filing Discovery
    "DiscoveryAgent",
    "DiscoveryAgentInput",
    "DiscoveryOutput",
    "DiscoveredEvent",
    "CompanyTarget",
    # Research & Verification
    "VerificationAgent",
    "VerificationAgentInput",
    "VerificationOutput",
    "VerifiedEvent",
    "VerifiedFact",
    # Portfolio Impact
    "ImpactAgent",
    "ImpactAgentInput",
    "PortfolioImpactReport",
    "HoldingImpact",
    # Alert & Reporting
    "ReportingAgent",
    "ReportingAgentInput",
    "MonitoringReport",
    "StructuredAlertItem",
]

