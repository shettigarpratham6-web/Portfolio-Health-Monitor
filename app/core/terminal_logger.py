"""
Portfolio Health Monitor
Terminal Observability & Real-Time Agent Execution Logger
Provides high-visibility, structured, real-time terminal output for autonomous monitoring
workflows and AI Copilot interactions. Never exposes sensitive keys or credentials.
"""

from datetime import datetime, timezone
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agentx.terminal")

# ------------------------------------------------------------------------------
# ANSI Styling & Colors
# ------------------------------------------------------------------------------
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Foreground Colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright Foreground
    BRIGHT_BLACK = "\033[90m"   # Gray
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_EMERALD = "\033[48;5;29m"
    BG_DARK = "\033[48;5;234m"
    BG_BLUE = "\033[48;5;24m"
    BG_PURPLE = "\033[48;5;54m"


# Sensitive patterns to scrub
SENSITIVE_PATTERNS = [
    re.compile(r"api[-_]?key", re.I),
    re.compile(r"secret", re.I),
    re.compile(r"token", re.I),
    re.compile(r"password", re.I),
    re.compile(r"auth(orization)?", re.I),
    re.compile(r"credential", re.I),
    re.compile(r"cookie", re.I),
]


def sanitize_value(key: str, val: Any) -> Any:
    """Mask any sensitive field value."""
    key_str = str(key)
    if any(pat.search(key_str) for pat in SENSITIVE_PATTERNS):
        return "******"
    if isinstance(val, dict):
        return {k: sanitize_value(k, v) for k, v in val.items()}
    if isinstance(val, list):
        return [sanitize_value("", item) for item in val]
    return val


def get_timestamp() -> str:
    """Return local formatted timestamp."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _emit(text: str) -> None:
    """Emit formatted string to stdout with immediate flush."""
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except Exception:
        pass


class TerminalLogger:
    """
    Dedicated terminal logger for real-time visibility into multi-agent
    monitoring runs and interactive AI Copilot queries.
    """

    # Width for separator lines
    LINE_WIDTH = 76

    @classmethod
    def log_workflow_start(
        cls,
        portfolio_id: str,
        portfolio_name: Optional[str] = None,
        user_email: Optional[str] = None,
        tickers: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Banner when the autonomous multi-agent workflow is triggered."""
        ts = get_timestamp()
        p_name = portfolio_name or "Active Portfolio"
        cfg = config or {}

        _emit("\n" + Colors.BRIGHT_CYAN + "╔" + "═" * (cls.LINE_WIDTH - 2) + "╗" + Colors.RESET)
        _emit(
            f"{Colors.BRIGHT_CYAN}║ {Colors.BOLD}{Colors.WHITE}🚀 AUTONOMOUS MULTI-AGENT MONITORING TRIGGERED{Colors.RESET}"
            + " " * (cls.LINE_WIDTH - 49)
            + f"{Colors.BRIGHT_CYAN}║{Colors.RESET}"
        )
        _emit(f"{Colors.BRIGHT_CYAN}╠" + "═" * (cls.LINE_WIDTH - 2) + "╣" + Colors.RESET)
        _emit(f"{Colors.BRIGHT_CYAN}║{Colors.RESET}  {Colors.BOLD}Timestamp:{Colors.RESET}      {ts} (Local)")
        _emit(f"{Colors.BRIGHT_CYAN}║{Colors.RESET}  {Colors.BOLD}Portfolio:{Colors.RESET}      {Colors.BRIGHT_WHITE}{p_name}{Colors.RESET} (ID: {portfolio_id})")
        if user_email:
            _emit(f"{Colors.BRIGHT_CYAN}║{Colors.RESET}  {Colors.BOLD}User Context:{Colors.RESET}   {user_email}")
        if tickers:
            _emit(f"{Colors.BRIGHT_CYAN}║{Colors.RESET}  {Colors.BOLD}Target Tickers:{Colors.RESET} {', '.join(tickers)}")
        _emit(
            f"{Colors.BRIGHT_CYAN}║{Colors.RESET}  {Colors.BOLD}Configuration:{Colors.RESET}  "
            f"News={cfg.get('include_news', True)} (max {cfg.get('max_news_per_target', 3)}) | "
            f"Filings={cfg.get('include_filings', True)} (max {cfg.get('max_filings_per_target', 2)}) | "
            f"Persist={cfg.get('persist_alerts', True)}"
        )
        _emit(f"{Colors.BRIGHT_CYAN}║{Colors.RESET}  {Colors.BOLD}Orchestration:{Colors.RESET}  LangGraph StateGraph Engine (6 Autonomous Agents)")
        _emit(Colors.BRIGHT_CYAN + "╚" + "═" * (cls.LINE_WIDTH - 2) + "╝" + Colors.RESET + "\n")

    @classmethod
    def log_agent_start(
        cls,
        agent_name: str,
        agent_role: str,
        icon: str = "🤖",
        phase_num: Optional[int] = None,
        total_phases: int = 6,
    ) -> None:
        """Banner when a specific agent begins execution."""
        ts = get_timestamp()
        phase_str = f"Phase {phase_num}/{total_phases} · " if phase_num else ""
        _emit(
            f"{Colors.BRIGHT_BLUE}╭── {icon} {Colors.BOLD}{Colors.BRIGHT_WHITE}{agent_name.upper()}{Colors.RESET} "
            f"{Colors.DIM}[{phase_str}{agent_role}]{Colors.RESET} "
            + "─" * max(2, cls.LINE_WIDTH - len(agent_name) - len(agent_role) - len(phase_str) - 16)
        )
        _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}  {Colors.DIM}Started at {ts}{Colors.RESET}")

    @classmethod
    def log_agent_step(cls, message: str, level: str = "info") -> None:
        """Log a descriptive execution step within an active agent."""
        bullet = f"{Colors.BRIGHT_GREEN}▶{Colors.RESET}" if level == "info" else f"{Colors.BRIGHT_YELLOW}⚡{Colors.RESET}"
        _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}  {bullet} {message}")

    @classmethod
    def log_tool_invocation(
        cls,
        tool_name: str,
        server_name: str,
        arguments: Dict[str, Any],
    ) -> None:
        """Log an MCP or internal tool invocation with sanitized arguments."""
        sanitized_args = sanitize_value("", arguments)
        args_str = ", ".join(f"{k}={v!r}" for k, v in sanitized_args.items() if k != "portfolio_id")
        if not args_str:
            args_str = "()"
        elif len(args_str) > 70:
            args_str = args_str[:67] + "..."

        _emit(
            f"{Colors.BRIGHT_BLUE}│{Colors.RESET}  {Colors.BRIGHT_YELLOW}⚙ Tool Call:{Colors.RESET} "
            f"{Colors.BOLD}{tool_name}{Colors.RESET} {Colors.DIM}(MCP: {server_name}){Colors.RESET}"
        )
        _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}    {Colors.DIM}↳ Args: {args_str}{Colors.RESET}")

    @classmethod
    def log_tool_result(cls, tool_name: str, summary: str, details: Optional[List[str]] = None) -> None:
        """Log the result data retrieved from a tool execution."""
        _emit(
            f"{Colors.BRIGHT_BLUE}│{Colors.RESET}    {Colors.BRIGHT_GREEN}✔ Return ({tool_name}):{Colors.RESET} {summary}"
        )
        if details:
            for d in details[:5]:  # Limit to 5 lines for concise readability
                _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}      {Colors.DIM}• {d}{Colors.RESET}")
            if len(details) > 5:
                _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}      {Colors.DIM}... and {len(details) - 5} more items{Colors.RESET}")

    @classmethod
    def log_api_call(
        cls,
        api_name: str,
        query: str,
        endpoint_or_model: Optional[str] = None,
    ) -> None:
        """Log an external API request (e.g., Tavily search, OpenRouter LLM)."""
        model_str = f" [{endpoint_or_model}]" if endpoint_or_model else ""
        _emit(
            f"{Colors.BRIGHT_BLUE}│{Colors.RESET}  {Colors.BRIGHT_MAGENTA}🌐 External API:{Colors.RESET} "
            f"{Colors.BOLD}{api_name}{model_str}{Colors.RESET}"
        )
        clean_q = query.strip()
        if len(clean_q) > 80:
            clean_q = clean_q[:77] + "..."
        _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}    {Colors.DIM}↳ Query/Prompt: \"{clean_q}\"{Colors.RESET}")

    @classmethod
    def log_agent_finish(
        cls,
        agent_name: str,
        duration_ms: float,
        status: str = "SUCCESS",
        summary: Optional[str] = None,
        key_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Banner when a specific agent finishes its task."""
        dur_str = f"{duration_ms:.1f}ms" if duration_ms < 1000 else f"{duration_ms/1000:.2f}s"
        status_color = Colors.BRIGHT_GREEN if status == "SUCCESS" else Colors.BRIGHT_RED
        status_icon = "✔" if status == "SUCCESS" else "✖"

        if summary:
            _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}  {Colors.BOLD}Outcome:{Colors.RESET} {summary}")

        if key_metrics:
            metrics_str = " | ".join(f"{k}: {v}" for k, v in key_metrics.items())
            _emit(f"{Colors.BRIGHT_BLUE}│{Colors.RESET}  {Colors.DIM}Metrics: {metrics_str}{Colors.RESET}")

        _emit(
            f"{Colors.BRIGHT_BLUE}╰── {status_color}{status_icon} {status}{Colors.RESET} "
            f"{Colors.DIM}completed in {Colors.BOLD}{dur_str}{Colors.RESET} "
            + "─" * max(2, cls.LINE_WIDTH - len(status) - len(dur_str) - 22)
            + "\n"
        )

    @classmethod
    def log_agent_error(cls, agent_name: str, error: str) -> None:
        """Log an error encountered within an agent."""
        _emit(f"{Colors.BRIGHT_RED}│  ✖ ERROR in {agent_name}: {error}{Colors.RESET}")

    @classmethod
    def log_workflow_finish(
        cls,
        portfolio_id: str,
        status: str,
        total_duration_ms: float,
        summary_stats: Dict[str, Any],
        errors: Optional[List[str]] = None,
    ) -> None:
        """Banner when the entire multi-agent workflow reaches completion."""
        ts = get_timestamp()
        dur_str = f"{total_duration_ms/1000:.2f}s"
        is_success = status in ("SUCCESS", "PARTIAL_SUCCESS")
        border_color = Colors.BRIGHT_GREEN if is_success else Colors.BRIGHT_RED

        _emit(border_color + "╔" + "═" * (cls.LINE_WIDTH - 2) + "╗" + Colors.RESET)
        _emit(
            f"{border_color}║ {Colors.BOLD}{Colors.WHITE}🏁 WORKFLOW EXECUTION COMPLETE{Colors.RESET}"
            + " " * (cls.LINE_WIDTH - 33)
            + f"{border_color}║{Colors.RESET}"
        )
        _emit(f"{border_color}╠" + "═" * (cls.LINE_WIDTH - 2) + "╣" + Colors.RESET)
        _emit(f"{border_color}║{Colors.RESET}  {Colors.BOLD}Final Status:{Colors.RESET}   {border_color}{Colors.BOLD}{status}{Colors.RESET}")
        _emit(f"{border_color}║{Colors.RESET}  {Colors.BOLD}Total Time:{Colors.RESET}     {dur_str} (Finished: {ts})")
        _emit(f"{border_color}║{Colors.RESET}  {Colors.BOLD}Portfolio ID:{Colors.RESET}   {portfolio_id}")
        _emit(
            f"{border_color}║{Colors.RESET}  {Colors.BOLD}Pipeline Results:{Colors.RESET} "
            f"Discoveries: {summary_stats.get('discovered_count', 0)} | "
            f"Verified: {summary_stats.get('verified_count', 0)} | "
            f"Impacts: {summary_stats.get('impacts_count', 0)} | "
            f"Alerts: {summary_stats.get('alerts_count', 0)}"
        )
        if "aggregate_risk" in summary_stats:
            risk_color = (
                Colors.BRIGHT_RED if summary_stats["aggregate_risk"] in ("CRITICAL", "HIGH")
                else Colors.BRIGHT_GREEN
            )
            _emit(
                f"{border_color}║{Colors.RESET}  {Colors.BOLD}Portfolio Risk:{Colors.RESET}   "
                f"{risk_color}{Colors.BOLD}{summary_stats['aggregate_risk']}{Colors.RESET}"
            )
        if errors:
            _emit(f"{border_color}║{Colors.RESET}  {Colors.BRIGHT_RED}Errors Encountered ({len(errors)}):{Colors.RESET}")
            for err in errors[:3]:
                _emit(f"{border_color}║{Colors.RESET}    • {err[:68]}")
        _emit(f"{border_color}║{Colors.RESET}  {Colors.DIM}SEC Non-Advisory Mandate Verified · Audit Persistence Completed{Colors.RESET}")
        _emit(border_color + "╚" + "═" * (cls.LINE_WIDTH - 2) + "╝" + Colors.RESET + "\n")

    # --------------------------------------------------------------------------
    # AI Copilot Logging
    # --------------------------------------------------------------------------
    @classmethod
    def log_copilot_start(
        cls,
        portfolio_id: str,
        portfolio_name: str,
        query: str,
    ) -> None:
        """Banner when the user asks a question to AI Copilot."""
        ts = get_timestamp()
        _emit("\n" + Colors.BRIGHT_MAGENTA + "┌" + "─" * (cls.LINE_WIDTH - 2) + "┐" + Colors.RESET)
        _emit(
            f"{Colors.BRIGHT_MAGENTA}│ {Colors.BOLD}{Colors.WHITE}💬 AI PORTFOLIO COPILOT INVOCATION{Colors.RESET}"
            + " " * (cls.LINE_WIDTH - 36)
            + f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}"
        )
        _emit(f"{Colors.BRIGHT_MAGENTA}├" + "─" * (cls.LINE_WIDTH - 2) + "┤" + Colors.RESET)
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.BOLD}Timestamp:{Colors.RESET}     {ts}")
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.BOLD}Portfolio:{Colors.RESET}     {Colors.BRIGHT_WHITE}{portfolio_name}{Colors.RESET} (ID: {portfolio_id})")
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.BOLD}User Query:{Colors.RESET}    {Colors.BRIGHT_YELLOW}\"{query}\"{Colors.RESET}")
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.DIM}Analyzing holdings, allocation weights, and recent risk alerts...{Colors.RESET}")

    @classmethod
    def log_copilot_step(cls, step_name: str, detail: str) -> None:
        """Log an intermediate step in AI Copilot query handling."""
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.BRIGHT_CYAN}↳ {step_name}:{Colors.RESET} {detail}")

    @classmethod
    def log_copilot_finish(
        cls,
        answer: str,
        cited_holdings: List[str],
        duration_ms: float,
        is_fast_path: bool = False,
        is_cached: bool = False,
    ) -> None:
        """Banner when AI Copilot completes answering."""
        dur_str = f"{duration_ms:.1f}ms" if duration_ms < 1000 else f"{duration_ms/1000:.2f}s"
        exec_mode = (
            f"{Colors.BRIGHT_GREEN}⚡ FAST-PATH DETERMINISTIC (0 tokens){Colors.RESET}"
            if is_fast_path
            else (
                f"{Colors.BRIGHT_CYAN}⚡ MEMORY CACHED (0 tokens){Colors.RESET}"
                if is_cached
                else f"{Colors.BRIGHT_YELLOW}🤖 LLM REASONING (OpenRouter / Token-Optimized){Colors.RESET}"
            )
        )
        clean_ans = answer.strip().replace("\n", " ")
        if len(clean_ans) > 130:
            clean_ans = clean_ans[:127] + "..."

        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.BOLD}Execution Mode:{Colors.RESET} {exec_mode}")
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.BOLD}Generated Answer:{Colors.RESET}")
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}    {Colors.WHITE}\"{clean_ans}\"{Colors.RESET}")
        if cited_holdings:
            _emit(
                f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.BOLD}Cited Holdings:{Colors.RESET} "
                + ", ".join(f"{Colors.BRIGHT_GREEN}[{c}]{Colors.RESET}" for c in cited_holdings)
            )
        _emit(f"{Colors.BRIGHT_MAGENTA}│{Colors.RESET}  {Colors.DIM}Latency: {dur_str} · Non-Advisory Certified{Colors.RESET}")
        _emit(Colors.BRIGHT_MAGENTA + "└" + "─" * (cls.LINE_WIDTH - 2) + "┘" + Colors.RESET + "\n")

