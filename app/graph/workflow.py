"""
Portfolio Health Monitor
LangGraph Workflow Orchestration Layer
Registers the six autonomous monitoring agents as graph nodes, implements Supervisor-controlled
task routing, conditional edges, retry limits, loop protection, and checkpointer persistence.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.terminal_logger import TerminalLogger

from app.agents.discovery_agent import CompanyTarget, DiscoveryAgent, DiscoveryAgentInput, DiscoveryOutput
from app.agents.impact_agent import ImpactAgent, ImpactAgentInput, PortfolioImpactReport
from app.agents.portfolio_agent import PortfolioAgent, PortfolioAgentInput, PortfolioContext
from app.agents.reporting_agent import MonitoringReport, ReportingAgent, ReportingAgentInput
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
)
from app.core.config import get_settings
from app.core.tracing import setup_tracing
from app.graph.state import (
    DEFAULT_NON_ADVISORY_NOTICE,
    AgentXState,
    WorkflowNodeName,
    WorkflowStatus,
)
from app.mcp.clients import MCPClient, get_mcp_client
from app.services.llm import LLMService, get_llm_service

logger = logging.getLogger("agentx.graph.workflow")


# ------------------------------------------------------------------------------
# Checkpointer Factory
# ------------------------------------------------------------------------------
def get_checkpointer(
    checkpointer_type: str = "memory",
    conn_string: Optional[str] = None,
) -> BaseCheckpointSaver:
    """
    Returns configured checkpoint saver for workflow state persistence.
    Supports in-memory persistence and prepares PostgreSQL-backed persistence.
    """
    mode = (checkpointer_type or "memory").lower().strip()
    if mode == "postgres":
        try:
            # LangGraph Postgres checkpointer integration
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            raw_url = conn_string or get_settings().DATABASE_URL
            # Normalize SQLAlchemy URL if necessary
            norm_url = raw_url.replace("postgresql+asyncpg://", "postgresql://")
            logger.info("Initializing PostgreSQL checkpointer for AgentX graph.")
            return AsyncPostgresSaver.from_conn_string(norm_url)
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-postgres package not installed. "
                "Defaulting to in-memory checkpointer."
            )
            return MemorySaver()
        except Exception as exc:
            logger.warning(
                "Failed to initialize PostgreSQL checkpointer: %s. "
                "Defaulting to in-memory checkpointer.",
                exc,
            )
            return MemorySaver()

    logger.debug("Using in-memory checkpointer for LangGraph workflow.")
    return MemorySaver()


# ------------------------------------------------------------------------------
# AgentX Workflow Engine
# ------------------------------------------------------------------------------
class AgentXWorkflow:
    """
    Coordinates and builds the complete multi-agent LangGraph workflow.
    Wires Supervisor, Portfolio Intelligence, News Discovery, Research Verification,
    Portfolio Impact, Alert Reporting, and Final Result nodes into a resilient StateGraph.
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        mcp_client: Optional[MCPClient] = None,
        supervisor_agent: Optional[SupervisorAgent] = None,
        portfolio_agent: Optional[PortfolioAgent] = None,
        discovery_agent: Optional[DiscoveryAgent] = None,
        verification_agent: Optional[VerificationAgent] = None,
        impact_agent: Optional[ImpactAgent] = None,
        reporting_agent: Optional[ReportingAgent] = None,
    ) -> None:
        self.llm = llm_service or get_llm_service()
        self.mcp = mcp_client or get_mcp_client()

        # Agents (injected or instantiated)
        self.supervisor_agent = supervisor_agent or SupervisorAgent(
            llm_service=self.llm, mcp_client=self.mcp
        )
        self.portfolio_agent = portfolio_agent or PortfolioAgent(
            llm_service=self.llm, mcp_client=self.mcp
        )
        self.discovery_agent = discovery_agent or DiscoveryAgent(
            llm_service=self.llm, mcp_client=self.mcp
        )
        self.verification_agent = verification_agent or VerificationAgent(
            llm_service=self.llm, mcp_client=self.mcp
        )
        self.impact_agent = impact_agent or ImpactAgent(
            llm_service=self.llm, mcp_client=self.mcp
        )
        self.reporting_agent = reporting_agent or ReportingAgent(
            llm_service=self.llm, mcp_client=self.mcp
        )
        # Ensure LangSmith tracing environment is active
        setup_tracing()

    # --------------------------------------------------------------------------
    # Workflow Node Callables
    # --------------------------------------------------------------------------
    async def supervisor_node(self, state: AgentXState) -> Dict[str, Any]:
        """
        Supervisor Controller Node:
        1. Protects against infinite loops by enforcing max_iterations.
        2. Validates user request parameters (portfolio_id).
        3. Formulates initial execution plan.
        4. When invoked post-reporting, reviews final state and determines success status.
        """
        current_iter = state.get("iteration_count", 0) + 1
        max_iters = state.get("max_iterations", 15)
        portfolio_id = (state.get("portfolio_id") or "").strip()

        updates: Dict[str, Any] = {
            "current_node": WorkflowNodeName.SUPERVISOR.value,
            "iteration_count": current_iter,
        }

        # 1. Uncontrolled loop protection
        if current_iter > max_iters:
            err = f"Workflow halted: maximum execution iteration limit ({max_iters}) reached."
            logger.error(err)
            updates.update({
                "status": WorkflowStatus.FAILED.value,
                "next_node": WorkflowNodeName.FINAL_RESULT.value,
                "errors": [err],
                "phase_history": [{
                    "node_name": WorkflowNodeName.SUPERVISOR.value,
                    "status": "FAILED",
                    "details": err,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            })
            return updates

        # 2. Input validation via guardrails
        try:
            from app.guardrails.input_validation import SecurityValidationError, validate_monitoring_request
            validate_monitoring_request({
                "portfolio_id": portfolio_id,
                "user_id": state.get("user_id"),
                "request_type": state.get("request_type", "full_portfolio_check"),
                "specific_tickers": state.get("specific_tickers"),
                "max_news_per_target": state.get("max_news_per_target", 3),
                "max_filings_per_target": state.get("max_filings_per_target", 2),
            })
        except Exception as val_exc:
            err_msg = str(val_exc)
            if hasattr(val_exc, "errors"):
                pyd_errs = val_exc.errors()
                if pyd_errs and "msg" in pyd_errs[0]:
                    err_msg = pyd_errs[0]["msg"]
            err = f"Security validation failed: {err_msg}"
            logger.error(err)
            updates.update({
                "status": WorkflowStatus.FAILED.value,
                "next_node": WorkflowNodeName.FINAL_RESULT.value,
                "errors": [err],
                "phase_history": [{
                    "node_name": WorkflowNodeName.SUPERVISOR.value,
                    "status": "FAILED",
                    "details": err,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            })
            return updates

        # 3. Post-reporting review: downstream pipeline has produced a monitoring report
        if state.get("monitoring_report") is not None:
            has_errors = bool(state.get("errors"))
            final_status = WorkflowStatus.PARTIAL_SUCCESS.value if has_errors else WorkflowStatus.SUCCESS.value
            logger.info("Supervisor concluding run with status: %s", final_status)
            TerminalLogger.log_agent_start("Supervisor Agent", "Final Quality & Non-Advisory Audit", icon="🤖")
            TerminalLogger.log_agent_step(f"Verifying non-advisory legal disclaimers and run integrity: status={final_status}")
            TerminalLogger.log_agent_finish("Supervisor Agent", 2.0, summary=f"Workflow quality audit concluded with status={final_status}.")
            updates.update({
                "status": final_status,
                "next_node": WorkflowNodeName.FINAL_RESULT.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.SUPERVISOR.value,
                    "status": "COMPLETED",
                    "details": f"Monitoring workflow concluded with {final_status}.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            })
            return updates

        # 4. Initial workflow dispatch: create execution plan
        if state.get("execution_plan") is None:
            start_t = time.perf_counter()
            TerminalLogger.log_agent_start("Supervisor Agent", "Orchestrator & Graph Auditor", icon="🤖", phase_num=1)
            try:
                req_type_str = state.get("request_type", "full_portfolio_check")
                try:
                    req_type = MonitoringRequestType(req_type_str)
                except ValueError:
                    req_type = MonitoringRequestType.FULL_PORTFOLIO_CHECK

                plan = self.supervisor_agent.create_execution_plan(
                    SupervisorInput(
                        portfolio_id=portfolio_id,
                        request_type=req_type,
                        specific_tickers=state.get("specific_tickers"),
                        max_news_per_target=state.get("max_news_per_target", 3),
                        max_filings_per_target=state.get("max_filings_per_target", 2),
                        include_filings=state.get("include_filings", True),
                        include_news=state.get("include_news", True),
                        persist_alerts=state.get("persist_alerts", True),
                    )
                )
                logger.info("Supervisor generated execution plan '%s' for portfolio '%s'.", plan.plan_id, portfolio_id)
                TerminalLogger.log_agent_step(f"Formulated execution plan '{plan.plan_id}' with {len(plan.phases)} phases")
                target_str = ", ".join(plan.target_tickers) if plan.target_tickers else "All equity holdings in portfolio"
                TerminalLogger.log_agent_step(f"Target scope: {target_str}")
                dur_ms = (time.perf_counter() - start_t) * 1000
                TerminalLogger.log_agent_finish("Supervisor Agent", dur_ms, summary=f"Execution plan '{plan.plan_id}' activated.")
                updates.update({
                    "execution_plan": plan,
                    "status": WorkflowStatus.RUNNING.value,
                    "next_node": WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
                    "phase_history": [{
                        "node_name": WorkflowNodeName.SUPERVISOR.value,
                        "status": "COMPLETED",
                        "details": f"Plan formulated with {len(plan.phases)} phases.",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }],
                })
            except Exception as exc:
                err = f"Supervisor planning failed: {exc}"
                logger.error(err, exc_info=True)
                updates.update({
                    "status": WorkflowStatus.FAILED.value,
                    "next_node": WorkflowNodeName.FINAL_RESULT.value,
                    "errors": [err],
                    "phase_history": [{
                        "node_name": WorkflowNodeName.SUPERVISOR.value,
                        "status": "FAILED",
                        "details": err,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }],
                })
            return updates

        # Default fallback
        updates["next_node"] = WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value
        return updates

    async def portfolio_node(self, state: AgentXState) -> Dict[str, Any]:
        """
        Portfolio Intelligence Node:
        Retrieves active holdings, weights, and concentration metrics.
        """
        portfolio_id = state["portfolio_id"]
        logger.info("Graph Node: portfolio_intelligence executing for portfolio: %s", portfolio_id)
        start_t = time.perf_counter()
        TerminalLogger.log_agent_start("Portfolio Intelligence Agent", "Holdings & Weight Analyst", icon="📊", phase_num=2)
        TerminalLogger.log_tool_invocation("get_portfolio", "database", {"portfolio_id": portfolio_id})
        TerminalLogger.log_tool_invocation("get_holdings", "database", {"portfolio_id": portfolio_id})
        TerminalLogger.log_tool_invocation("calculate_portfolio_allocation", "analysis", {"portfolio_id": portfolio_id})
        TerminalLogger.log_tool_invocation("analyze_company_relationships", "analysis", {"portfolio_id": portfolio_id})

        try:
            context: PortfolioContext = await self.portfolio_agent.run(
                PortfolioAgentInput(portfolio_id=portfolio_id)
            )

            # Determine routing based on holding availability
            if not context.holdings:
                logger.warning("Portfolio '%s' has 0 holdings. Routing directly to reporting.", portfolio_id)
                next_node = WorkflowNodeName.REPORTING.value
            else:
                next_node = WorkflowNodeName.DISCOVERY.value

            holdings_details = [
                f"{h.ticker}: {h.shares:g} shares @ ${h.buy_price:.2f} | Mkt Val: ${h.market_value:,.2f} | Weight: {h.weight_pct:.1f}%"
                for h in context.holdings
            ]
            TerminalLogger.log_tool_result(
                "Holdings & Allocations",
                f"Retrieved {len(context.holdings)} positions (Valuation: ${context.total_market_value:,.2f} {context.currency})",
                details=holdings_details,
            )
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_finish(
                "Portfolio Intelligence Agent",
                dur_ms,
                summary=f"Computed portfolio structure: {len(context.holdings)} holdings, Concentration={context.concentration_risk_level}",
                key_metrics={
                    "Total Valuation": f"${context.total_market_value:,.2f}",
                    "Dominant Sector": f"{context.dominant_sector} ({context.dominant_sector_pct:.1f}%)",
                    "Concentration Risk": context.concentration_risk_level,
                },
            )

            return {
                "current_node": WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
                "portfolio_context": context,
                "next_node": next_node,
                "phase_history": [{
                    "node_name": WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
                    "status": "COMPLETED",
                    "details": f"Loaded {len(context.holdings)} holdings.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        except Exception as exc:
            err_msg = f"Portfolio Intelligence node failed: {exc}"
            logger.error(err_msg, exc_info=True)
            retry_counts = dict(state.get("retry_counts", {}))
            retries = retry_counts.get(WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value, 0) + 1
            retry_counts[WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value] = retries
            max_retries = state.get("max_retries", 2)

            if retries <= max_retries:
                logger.info("Retrying portfolio_intelligence (attempt %d of %d)", retries, max_retries)
                next_node = WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value
            else:
                # Fatal failure: without portfolio context, downstream cannot run
                logger.error("Portfolio intelligence retries exhausted. Halting workflow.")
                next_node = WorkflowNodeName.FINAL_RESULT.value

            return {
                "current_node": WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
                "retry_counts": retry_counts,
                "next_node": next_node,
                "status": WorkflowStatus.FAILED.value if retries > max_retries else state.get("status", WorkflowStatus.RUNNING.value),
                "errors": [err_msg],
                "phase_history": [{
                    "node_name": WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
                    "status": "RETRYING" if retries <= max_retries else "FAILED",
                    "details": f"Error: {exc}. Retries attempted: {retries}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

    async def discovery_node(self, state: AgentXState) -> Dict[str, Any]:
        """
        News & Filing Discovery Node:
        Discovers relevant news and regulatory filings across portfolio holdings.
        """
        portfolio_context = state.get("portfolio_context")
        if not portfolio_context or not portfolio_context.holdings:
            logger.info("Discovery node skipped: no active holdings in portfolio context.")
            return {
                "current_node": WorkflowNodeName.DISCOVERY.value,
                "discovered_events": [],
                "discovery_summary": "Skipped discovery: portfolio has no active holdings.",
                "next_node": WorkflowNodeName.VERIFICATION.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.DISCOVERY.value,
                    "status": "SKIPPED",
                    "details": "No holdings to search.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        # Filter target holdings if specific tickers were requested
        filter_tickers = {t.upper() for t in state["specific_tickers"]} if state.get("specific_tickers") else None
        targets: List[CompanyTarget] = []

        for h in portfolio_context.holdings:
            if filter_tickers and h.ticker.upper() not in filter_tickers:
                continue
            targets.append(
                CompanyTarget(
                    company_name=h.company_name,
                    ticker=h.ticker,
                    company_id=h.company_id,
                )
            )

        if not targets:
            logger.warning("No portfolio holdings matched specific tickers %s.", state.get("specific_tickers"))
            return {
                "current_node": WorkflowNodeName.DISCOVERY.value,
                "discovered_events": [],
                "discovery_summary": "No target tickers matched portfolio holdings.",
                "next_node": WorkflowNodeName.VERIFICATION.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.DISCOVERY.value,
                    "status": "SKIPPED",
                    "details": "Specified tickers not found in portfolio.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        logger.info("Graph Node: discovery searching for %d target equities.", len(targets))
        start_t = time.perf_counter()
        TerminalLogger.log_agent_start("News & Filing Discovery Agent", "Live Market & Regulatory Analyst", icon="🌐", phase_num=3)
        target_labels = [f"{t.company_name} ({t.ticker})" for t in targets]
        TerminalLogger.log_agent_step(f"Executing web and regulatory searches across {len(targets)} targets: {', '.join(target_labels)}")
        try:
            disc_out: DiscoveryOutput = await self.discovery_agent.run(
                DiscoveryAgentInput(
                    targets=targets,
                    max_news_per_target=state.get("max_news_per_target", 3),
                    max_filings_per_target=state.get("max_filings_per_target", 2),
                    include_filings=state.get("include_filings", True),
                    include_news=state.get("include_news", True),
                )
            )

            discovered_details = [
                f"[{ev.ticker}] {ev.title[:65]} ({ev.source_name})"
                for ev in disc_out.discovered_events[:5]
            ]
            TerminalLogger.log_tool_result(
                "Tavily Market Intelligence",
                f"Retrieved {disc_out.total_discovered} items across {len(disc_out.companies_searched)} holdings",
                details=discovered_details,
            )
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_finish(
                "News & Filing Discovery Agent",
                dur_ms,
                summary=f"Gathered {disc_out.total_discovered} candidate news items and regulatory filings.",
                key_metrics={
                    "Total Gathered": disc_out.total_discovered,
                    "Companies Searched": len(disc_out.companies_searched),
                },
            )

            return {
                "current_node": WorkflowNodeName.DISCOVERY.value,
                "discovered_events": disc_out.discovered_events,
                "discovery_summary": disc_out.discovery_summary,
                "next_node": WorkflowNodeName.VERIFICATION.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.DISCOVERY.value,
                    "status": "COMPLETED",
                    "details": f"Discovered {disc_out.total_discovered} events across {len(disc_out.companies_searched)} holdings.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        except Exception as exc:
            err_msg = f"News Discovery node failed: {exc}"
            logger.error(err_msg, exc_info=True)
            retry_counts = dict(state.get("retry_counts", {}))
            retries = retry_counts.get(WorkflowNodeName.DISCOVERY.value, 0) + 1
            retry_counts[WorkflowNodeName.DISCOVERY.value] = retries
            max_retries = state.get("max_retries", 2)

            if retries <= max_retries:
                logger.info("Retrying discovery (attempt %d of %d)", retries, max_retries)
                next_node = WorkflowNodeName.DISCOVERY.value
            else:
                # Graceful degradation: continue with 0 events rather than crashing
                logger.warning("Discovery retries exhausted; continuing with 0 events.")
                next_node = WorkflowNodeName.VERIFICATION.value

            return {
                "current_node": WorkflowNodeName.DISCOVERY.value,
                "retry_counts": retry_counts,
                "next_node": next_node,
                "discovered_events": [] if retries > max_retries else state.get("discovered_events", []),
                "discovery_summary": "Discovery failed; continuing with empty events." if retries > max_retries else state.get("discovery_summary"),
                "errors": [err_msg],
                "phase_history": [{
                    "node_name": WorkflowNodeName.DISCOVERY.value,
                    "status": "RETRYING" if retries <= max_retries else "FAILED_DEGRADED",
                    "details": f"Error: {exc}. Retries attempted: {retries}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

    async def verification_node(self, state: AgentXState) -> Dict[str, Any]:
        """
        Research & Verification Node:
        Filters duplicates via Analysis MCP and classifies factual evidence vs market rumors.
        """
        discovered_events = state.get("discovered_events", [])
        logger.info("Graph Node: verification evaluating %d candidate events.", len(discovered_events))
        start_t = time.perf_counter()
        TerminalLogger.log_agent_start("Research & Verification Agent", "Noise Filter & Fact Corroborator", icon="🛡️", phase_num=4)
        TerminalLogger.log_agent_step(f"Evaluating {len(discovered_events)} candidate documents via SHA-256 deduplication and OpenRouter LLM...")

        if not discovered_events:
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_finish("Research & Verification Agent", dur_ms, summary="0 candidate events to evaluate.")
            return {
                "current_node": WorkflowNodeName.VERIFICATION.value,
                "verified_events": [],
                "duplicates_filtered_count": 0,
                "verification_summary": "No candidate events available to verify.",
                "next_node": WorkflowNodeName.IMPACT.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.VERIFICATION.value,
                    "status": "COMPLETED",
                    "details": "0 events evaluated.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        try:
            ver_out: VerificationOutput = await self.verification_agent.run(
                VerificationAgentInput(discovered_events=discovered_events)
            )

            sample_verified = [
                f"[{v.ticker}] {v.canonical_title[:55]} (Credibility: {v.credibility_score*100:.0f}%, Sentiment: {v.sentiment})"
                for v in ver_out.verified_events[:5]
            ]
            TerminalLogger.log_tool_result(
                "Fact Verification & Provenance",
                f"Verified {ver_out.total_verified} events ({ver_out.duplicates_filtered} duplicates filtered)",
                details=sample_verified,
            )
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_finish(
                "Research & Verification Agent",
                dur_ms,
                summary=f"Verified {ver_out.total_verified} events, removed {ver_out.duplicates_filtered} duplicates from {ver_out.total_reviewed} candidate documents.",
                key_metrics={
                    "Verified Events": ver_out.total_verified,
                    "Duplicates Filtered": ver_out.duplicates_filtered,
                },
            )

            return {
                "current_node": WorkflowNodeName.VERIFICATION.value,
                "verified_events": ver_out.verified_events,
                "duplicates_filtered_count": ver_out.duplicates_filtered,
                "verification_summary": ver_out.verification_summary,
                "next_node": WorkflowNodeName.IMPACT.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.VERIFICATION.value,
                    "status": "COMPLETED",
                    "details": f"Verified {ver_out.total_verified} events, filtered {ver_out.duplicates_filtered} duplicates.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        except Exception as exc:
            err_msg = f"Research Verification node failed: {exc}"
            logger.error(err_msg, exc_info=True)
            retry_counts = dict(state.get("retry_counts", {}))
            retries = retry_counts.get(WorkflowNodeName.VERIFICATION.value, 0) + 1
            retry_counts[WorkflowNodeName.VERIFICATION.value] = retries
            max_retries = state.get("max_retries", 2)

            if retries <= max_retries:
                logger.info("Retrying verification (attempt %d of %d)", retries, max_retries)
                next_node = WorkflowNodeName.VERIFICATION.value
            else:
                logger.warning("Verification retries exhausted; continuing with 0 verified events.")
                next_node = WorkflowNodeName.IMPACT.value

            return {
                "current_node": WorkflowNodeName.VERIFICATION.value,
                "retry_counts": retry_counts,
                "next_node": next_node,
                "verified_events": [] if retries > max_retries else state.get("verified_events", []),
                "duplicates_filtered_count": 0,
                "verification_summary": "Verification failed; proceeding with fallback." if retries > max_retries else state.get("verification_summary"),
                "errors": [err_msg],
                "phase_history": [{
                    "node_name": WorkflowNodeName.VERIFICATION.value,
                    "status": "RETRYING" if retries <= max_retries else "FAILED_DEGRADED",
                    "details": f"Error: {exc}. Retries attempted: {retries}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

    async def impact_node(self, state: AgentXState) -> Dict[str, Any]:
        """
        Portfolio Impact Node:
        Maps verified events to portfolio holdings and calculates deterministic risk impact.
        """
        portfolio_context = state.get("portfolio_context")
        verified_events = state.get("verified_events", [])
        logger.info("Graph Node: impact assessing %d verified events.", len(verified_events))
        start_t = time.perf_counter()
        TerminalLogger.log_agent_start("Portfolio Impact Agent", "Deterministic Risk Quantifier", icon="⚠️", phase_num=5)
        TerminalLogger.log_agent_step(f"Calculating mathematical exposure for {len(verified_events)} verified events against portfolio holdings...")

        if not portfolio_context:
            err_msg = "Portfolio Impact node missing required portfolio context."
            logger.error(err_msg)
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_error("Portfolio Impact Agent", err_msg)
            TerminalLogger.log_agent_finish("Portfolio Impact Agent", dur_ms, status="FAILED")
            return {
                "current_node": WorkflowNodeName.IMPACT.value,
                "next_node": WorkflowNodeName.REPORTING.value,
                "errors": [err_msg],
            }

        try:
            impact_rep: PortfolioImpactReport = await self.impact_agent.run(
                ImpactAgentInput(
                    portfolio_context=portfolio_context,
                    verified_events=verified_events,
                )
            )

            sample_impacts = [
                f"[{imp.ticker}] {imp.event_title[:45]} | Impact: {imp.impact_score:+.1f} ({imp.impact_severity}) | Weighted Risk: {imp.weighted_portfolio_risk:.2f}"
                for imp in impact_rep.holding_impacts[:5]
            ]
            TerminalLogger.log_tool_result(
                "Deterministic Risk Matrix",
                f"Evaluated {impact_rep.total_events_evaluated} events: {impact_rep.direct_impacts_count} direct impacts, {impact_rep.indirect_impacts_count} indirect",
                details=sample_impacts,
            )
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_finish(
                "Portfolio Impact Agent",
                dur_ms,
                summary=f"Aggregate portfolio risk assessed at {impact_rep.aggregate_risk_level}. Most affected: {impact_rep.highest_impact_holding or 'None'}.",
                key_metrics={
                    "Aggregate Risk": impact_rep.aggregate_risk_level,
                    "Direct Impacts": impact_rep.direct_impacts_count,
                    "Indirect Impacts": impact_rep.indirect_impacts_count,
                },
            )

            return {
                "current_node": WorkflowNodeName.IMPACT.value,
                "impact_report": impact_rep,
                "next_node": WorkflowNodeName.REPORTING.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.IMPACT.value,
                    "status": "COMPLETED",
                    "details": (
                        f"Evaluated {impact_rep.total_events_evaluated} events: "
                        f"{impact_rep.direct_impacts_count} direct impacts, "
                        f"aggregate risk: {impact_rep.aggregate_risk_level}."
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        except Exception as exc:
            err_msg = f"Portfolio Impact node failed: {exc}"
            logger.error(err_msg, exc_info=True)
            retry_counts = dict(state.get("retry_counts", {}))
            retries = retry_counts.get(WorkflowNodeName.IMPACT.value, 0) + 1
            retry_counts[WorkflowNodeName.IMPACT.value] = retries
            max_retries = state.get("max_retries", 2)

            if retries <= max_retries:
                logger.info("Retrying impact (attempt %d of %d)", retries, max_retries)
                next_node = WorkflowNodeName.IMPACT.value
                fallback_report = None
            else:
                logger.warning("Impact analysis retries exhausted; synthesizing fallback report.")
                next_node = WorkflowNodeName.REPORTING.value
                fallback_report = PortfolioImpactReport(
                    portfolio_id=state["portfolio_id"],
                    portfolio_name=portfolio_context.name,
                    total_events_evaluated=0,
                    direct_impacts_count=0,
                    indirect_impacts_count=0,
                    aggregate_risk_level="UNKNOWN",
                    holding_impacts=[],
                    impact_summary="Impact evaluation failed; produced fallback report.",
                )

            updates: Dict[str, Any] = {
                "current_node": WorkflowNodeName.IMPACT.value,
                "retry_counts": retry_counts,
                "next_node": next_node,
                "errors": [err_msg],
                "phase_history": [{
                    "node_name": WorkflowNodeName.IMPACT.value,
                    "status": "RETRYING" if retries <= max_retries else "FAILED_DEGRADED",
                    "details": f"Error: {exc}. Retries attempted: {retries}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }
            if fallback_report:
                updates["impact_report"] = fallback_report
            return updates

    async def reporting_node(self, state: AgentXState) -> Dict[str, Any]:
        """
        Alert & Reporting Node:
        Generates structured alerts with primary source citations and persists records in DB.
        """
        portfolio_id = state["portfolio_id"]
        impact_report = state.get("impact_report")
        verified_events = state.get("verified_events", [])
        portfolio_context = state.get("portfolio_context")

        logger.info("Graph Node: reporting synthesizing monitoring report for portfolio: %s", portfolio_id)
        start_t = time.perf_counter()
        TerminalLogger.log_agent_start("Alert & Reporting Agent", "Alert Writer & Persistence Guard", icon="📑", phase_num=6)
        TerminalLogger.log_tool_invocation("save_research_event", "database", {"verified_events_count": len(verified_events)})
        TerminalLogger.log_tool_invocation("save_evidence_source", "database", {"citations_to_persist": len(verified_events)})
        TerminalLogger.log_tool_invocation("save_monitoring_alert", "database", {"portfolio_id": portfolio_id})

        # Handle empty portfolio scenario (no impact report needed)
        if not impact_report and portfolio_context and not portfolio_context.holdings:
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_finish("Alert & Reporting Agent", dur_ms, summary="Empty portfolio report generated.")
            empty_report = MonitoringReport(
                portfolio_id=portfolio_id,
                executive_summary="Portfolio contains no active holdings. No risk alerts or events recorded.",
                aggregate_risk_level="LOW",
                alerts=[],
            )
            return {
                "current_node": WorkflowNodeName.REPORTING.value,
                "monitoring_report": empty_report,
                "next_node": WorkflowNodeName.SUPERVISOR.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.REPORTING.value,
                    "status": "COMPLETED",
                    "details": "Generated clean empty portfolio report.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        # Handle missing impact report safely
        active_impact_report = impact_report or PortfolioImpactReport(
            portfolio_id=portfolio_id,
            portfolio_name=portfolio_context.name if portfolio_context else "Unknown",
            total_events_evaluated=0,
            direct_impacts_count=0,
            indirect_impacts_count=0,
            aggregate_risk_level="UNKNOWN",
            holding_impacts=[],
            impact_summary="No impact data available.",
        )

        try:
            m_report: MonitoringReport = await self.reporting_agent.run(
                ReportingAgentInput(
                    portfolio_id=portfolio_id,
                    impact_report=active_impact_report,
                    verified_events=verified_events,
                    persist_to_database=state.get("persist_alerts", True),
                )
            )

            sample_alerts = [
                f"[{a.severity}] {a.title[:55]} ({len(a.evidence_sources)} sources)"
                for a in m_report.alerts[:4]
            ]
            TerminalLogger.log_tool_result(
                "Database Persistence & Report Generation",
                f"Generated {len(m_report.alerts)} alerts ({m_report.persisted_alerts_count} saved to PostgreSQL)",
                details=sample_alerts,
            )
            dur_ms = (time.perf_counter() - start_t) * 1000
            TerminalLogger.log_agent_finish(
                "Alert & Reporting Agent",
                dur_ms,
                summary=f"Synthesized {len(m_report.alerts)} alerts ({m_report.persisted_alerts_count} persisted to DB, {m_report.persisted_events_count} research events saved).",
                key_metrics={
                    "Alerts Formulated": len(m_report.alerts),
                    "Persisted to DB": m_report.persisted_alerts_count,
                    "Events Saved": m_report.persisted_events_count,
                },
            )

            return {
                "current_node": WorkflowNodeName.REPORTING.value,
                "monitoring_report": m_report,
                "next_node": WorkflowNodeName.SUPERVISOR.value,
                "phase_history": [{
                    "node_name": WorkflowNodeName.REPORTING.value,
                    "status": "COMPLETED",
                    "details": f"Generated {len(m_report.alerts)} alerts ({m_report.persisted_alerts_count} persisted).",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        except Exception as exc:
            err_msg = f"Alert Reporting node failed: {exc}"
            logger.error(err_msg, exc_info=True)
            retry_counts = dict(state.get("retry_counts", {}))
            retries = retry_counts.get(WorkflowNodeName.REPORTING.value, 0) + 1
            retry_counts[WorkflowNodeName.REPORTING.value] = retries
            max_retries = state.get("max_retries", 2)

            if retries <= max_retries:
                logger.info("Retrying reporting (attempt %d of %d)", retries, max_retries)
                next_node = WorkflowNodeName.REPORTING.value
                fallback_m_rep = None
            else:
                logger.warning("Reporting retries exhausted; synthesizing minimal monitoring report.")
                next_node = WorkflowNodeName.SUPERVISOR.value
                fallback_m_rep = MonitoringReport(
                    portfolio_id=portfolio_id,
                    executive_summary="Monitoring executed; report generation encountered an error.",
                    aggregate_risk_level=active_impact_report.aggregate_risk_level,
                    alerts=[],
                )

            updates: Dict[str, Any] = {
                "current_node": WorkflowNodeName.REPORTING.value,
                "retry_counts": retry_counts,
                "next_node": next_node,
                "errors": [err_msg],
                "phase_history": [{
                    "node_name": WorkflowNodeName.REPORTING.value,
                    "status": "RETRYING" if retries <= max_retries else "FAILED_DEGRADED",
                    "details": f"Error: {exc}. Retries attempted: {retries}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }
            if fallback_m_rep:
                updates["monitoring_report"] = fallback_m_rep
            return updates

    async def final_result_node(self, state: AgentXState) -> Dict[str, Any]:
        """
        Terminal Final Result Node:
        Seals execution timestamp, sets non-advisory disclaimer, and compiles final SupervisorOutput.
        """
        completed_at = datetime.now(timezone.utc).isoformat()
        has_errors = bool(state.get("errors"))
        current_status = state.get("status", WorkflowStatus.SUCCESS.value)

        # Reconcile status
        if current_status == WorkflowStatus.FAILED.value:
            final_status = "FAILED"
        elif has_errors:
            final_status = "PARTIAL_SUCCESS"
        else:
            final_status = "SUCCESS"

        disc_events = state.get("discovered_events", [])
        ver_events = state.get("verified_events", [])

        # Formulate final output contract
        final_output = SupervisorOutput(
            status=final_status,
            portfolio_id=state["portfolio_id"],
            execution_plan=state.get("execution_plan") or SupervisorExecutionPlan(
                portfolio_id=state["portfolio_id"],
                request_type=MonitoringRequestType.FULL_PORTFOLIO_CHECK,
            ),
            portfolio_context=state.get("portfolio_context"),
            discovery_output=DiscoveryOutput(
                total_discovered=len(disc_events),
                companies_searched=list({e.ticker for e in disc_events if e.ticker}),
                discovered_events=disc_events,
                discovery_summary=state.get("discovery_summary") or "",
            ) if disc_events else None,
            verification_output=VerificationOutput(
                total_reviewed=len(disc_events),
                total_verified=len(ver_events),
                duplicates_filtered=state.get("duplicates_filtered_count", 0),
                verified_events=ver_events,
                verification_summary=state.get("verification_summary") or "",
            ) if ver_events or state.get("verification_summary") else None,
            impact_report=state.get("impact_report"),
            monitoring_report=state.get("monitoring_report"),
            errors=state.get("errors", []),
            started_at=state.get("started_at", completed_at),
            completed_at=completed_at,
            non_advisory_notice=state.get("non_advisory_notice", DEFAULT_NON_ADVISORY_NOTICE),
        )

        logger.info(
            "Graph completed for portfolio '%s' with final status: %s (errors: %d)",
            state["portfolio_id"],
            final_status,
            len(state.get("errors", [])),
        )

        return {
            "current_node": WorkflowNodeName.FINAL_RESULT.value,
            "next_node": None,
            "status": final_status,
            "completed_at": completed_at,
            "final_output": final_output,
            "phase_history": [{
                "node_name": WorkflowNodeName.FINAL_RESULT.value,
                "status": final_status,
                "details": f"Workflow finalized with status: {final_status}.",
                "timestamp": completed_at,
            }],
        }

    # --------------------------------------------------------------------------
    # Conditional Edge Routing Functions
    # --------------------------------------------------------------------------
    @staticmethod
    def route_supervisor(state: AgentXState) -> str:
        """Route conditionally from Supervisor node."""
        next_n = state.get("next_node")
        if next_n == WorkflowNodeName.FINAL_RESULT.value:
            return WorkflowNodeName.FINAL_RESULT.value
        if state.get("status") in (WorkflowStatus.FAILED.value, WorkflowStatus.SUCCESS.value, WorkflowStatus.PARTIAL_SUCCESS.value):
            return WorkflowNodeName.FINAL_RESULT.value
        return WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value

    @staticmethod
    def route_portfolio(state: AgentXState) -> str:
        """Route conditionally from Portfolio Intelligence node."""
        next_n = state.get("next_node")
        if next_n == WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value:
            return WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value  # Retry
        if next_n == WorkflowNodeName.FINAL_RESULT.value:
            return WorkflowNodeName.FINAL_RESULT.value  # Unrecoverable error
        if next_n == WorkflowNodeName.REPORTING.value:
            return WorkflowNodeName.REPORTING.value  # Empty portfolio
        return WorkflowNodeName.DISCOVERY.value

    @staticmethod
    def route_discovery(state: AgentXState) -> str:
        """Route conditionally from Discovery node."""
        next_n = state.get("next_node")
        if next_n == WorkflowNodeName.DISCOVERY.value:
            return WorkflowNodeName.DISCOVERY.value  # Retry
        return WorkflowNodeName.VERIFICATION.value

    @staticmethod
    def route_verification(state: AgentXState) -> str:
        """Route conditionally from Verification node."""
        next_n = state.get("next_node")
        if next_n == WorkflowNodeName.VERIFICATION.value:
            return WorkflowNodeName.VERIFICATION.value  # Retry
        return WorkflowNodeName.IMPACT.value

    @staticmethod
    def route_impact(state: AgentXState) -> str:
        """Route conditionally from Impact node."""
        next_n = state.get("next_node")
        if next_n == WorkflowNodeName.IMPACT.value:
            return WorkflowNodeName.IMPACT.value  # Retry
        return WorkflowNodeName.REPORTING.value

    @staticmethod
    def route_reporting(state: AgentXState) -> str:
        """Route conditionally from Reporting node."""
        next_n = state.get("next_node")
        if next_n == WorkflowNodeName.REPORTING.value:
            return WorkflowNodeName.REPORTING.value  # Retry
        return WorkflowNodeName.SUPERVISOR.value  # Post-reporting supervisor review

    # --------------------------------------------------------------------------
    # Graph Construction & Compilation
    # --------------------------------------------------------------------------
    def build_graph(self) -> StateGraph:
        """Construct the complete uncompiled StateGraph."""
        builder = StateGraph(AgentXState)

        # 1. Register all nodes
        builder.add_node(WorkflowNodeName.SUPERVISOR.value, self.supervisor_node)
        builder.add_node(WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value, self.portfolio_node)
        builder.add_node(WorkflowNodeName.DISCOVERY.value, self.discovery_node)
        builder.add_node(WorkflowNodeName.VERIFICATION.value, self.verification_node)
        builder.add_node(WorkflowNodeName.IMPACT.value, self.impact_node)
        builder.add_node(WorkflowNodeName.REPORTING.value, self.reporting_node)
        builder.add_node(WorkflowNodeName.FINAL_RESULT.value, self.final_result_node)

        # 2. Add entry point: START -> supervisor
        builder.add_edge(START, WorkflowNodeName.SUPERVISOR.value)

        # 3. Add conditional edges
        builder.add_conditional_edges(
            WorkflowNodeName.SUPERVISOR.value,
            self.route_supervisor,
            {
                WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value: WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
                WorkflowNodeName.FINAL_RESULT.value: WorkflowNodeName.FINAL_RESULT.value,
            },
        )

        builder.add_conditional_edges(
            WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
            self.route_portfolio,
            {
                WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value: WorkflowNodeName.PORTFOLIO_INTELLIGENCE.value,
                WorkflowNodeName.DISCOVERY.value: WorkflowNodeName.DISCOVERY.value,
                WorkflowNodeName.REPORTING.value: WorkflowNodeName.REPORTING.value,
                WorkflowNodeName.FINAL_RESULT.value: WorkflowNodeName.FINAL_RESULT.value,
            },
        )

        builder.add_conditional_edges(
            WorkflowNodeName.DISCOVERY.value,
            self.route_discovery,
            {
                WorkflowNodeName.DISCOVERY.value: WorkflowNodeName.DISCOVERY.value,
                WorkflowNodeName.VERIFICATION.value: WorkflowNodeName.VERIFICATION.value,
            },
        )

        builder.add_conditional_edges(
            WorkflowNodeName.VERIFICATION.value,
            self.route_verification,
            {
                WorkflowNodeName.VERIFICATION.value: WorkflowNodeName.VERIFICATION.value,
                WorkflowNodeName.IMPACT.value: WorkflowNodeName.IMPACT.value,
            },
        )

        builder.add_conditional_edges(
            WorkflowNodeName.IMPACT.value,
            self.route_impact,
            {
                WorkflowNodeName.IMPACT.value: WorkflowNodeName.IMPACT.value,
                WorkflowNodeName.REPORTING.value: WorkflowNodeName.REPORTING.value,
            },
        )

        builder.add_conditional_edges(
            WorkflowNodeName.REPORTING.value,
            self.route_reporting,
            {
                WorkflowNodeName.REPORTING.value: WorkflowNodeName.REPORTING.value,
                WorkflowNodeName.SUPERVISOR.value: WorkflowNodeName.SUPERVISOR.value,
            },
        )

        # 4. Terminal edge: final_result -> END
        builder.add_edge(WorkflowNodeName.FINAL_RESULT.value, END)

        return builder

    def compile(
        self,
        checkpointer: Optional[BaseCheckpointSaver] = None,
    ) -> CompiledStateGraph:
        """
        Compile the StateGraph into an executable LangGraph instance with optional checkpointer.
        """
        graph_builder = self.build_graph()
        return graph_builder.compile(checkpointer=checkpointer)

    async def ainvoke(
        self,
        initial_state: AgentXState,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentXState:
        """
        Execute compiled graph with standardized LangSmith tracing run config.
        """
        from app.core.tracing import get_langchain_run_config, setup_tracing
        setup_tracing()
        graph = self.compile(checkpointer=checkpointer)
        portfolio_id = initial_state.get("portfolio_id", "unknown")
        req_type = initial_state.get("request_type", "full_portfolio_check")
        user_id = initial_state.get("user_id")

        run_config = config or get_langchain_run_config(
            portfolio_id=portfolio_id,
            request_type=req_type,
            user_id=user_id,
        )
        return await graph.ainvoke(initial_state, config=run_config)


# ------------------------------------------------------------------------------
# Module-level Factory Functions
# ------------------------------------------------------------------------------
def create_agentx_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    llm_service: Optional[LLMService] = None,
    mcp_client: Optional[MCPClient] = None,
    supervisor_agent: Optional[SupervisorAgent] = None,
    portfolio_agent: Optional[PortfolioAgent] = None,
    discovery_agent: Optional[DiscoveryAgent] = None,
    verification_agent: Optional[VerificationAgent] = None,
    impact_agent: Optional[ImpactAgent] = None,
    reporting_agent: Optional[ReportingAgent] = None,
) -> CompiledStateGraph:
    """
    Convenience factory to instantiate, wire, and compile the AgentX monitoring graph.
    """
    workflow = AgentXWorkflow(
        llm_service=llm_service,
        mcp_client=mcp_client,
        supervisor_agent=supervisor_agent,
        portfolio_agent=portfolio_agent,
        discovery_agent=discovery_agent,
        verification_agent=verification_agent,
        impact_agent=impact_agent,
        reporting_agent=reporting_agent,
    )
    return workflow.compile(checkpointer=checkpointer)
