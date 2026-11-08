"""
AgentX – Portfolio Health Monitor
Input Safety & Guardrails Validation
Validates user monitoring requests, MCP tool arguments, external research content,
and protects against prompt injections, SSRF, and SQL injection attempts.
"""

from enum import Enum
import ipaddress
import logging
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("agentx.guardrails.input")


# ------------------------------------------------------------------------------
# Security Exceptions
# ------------------------------------------------------------------------------
class SecurityValidationError(ValueError):
    """Base exception for input safety and security policy violations."""
    pass


class PromptInjectionDetectedError(SecurityValidationError):
    """Raised when an active prompt injection attack is detected in user input."""
    pass


class MaliciousInputError(SecurityValidationError):
    """Raised when SQL injection, path traversal, or command injection is detected."""
    pass


class SSRFAttemptError(SecurityValidationError):
    """Raised when a URL attempts to target private or loopback networks."""
    pass


# ------------------------------------------------------------------------------
# Injection Detection Signatures
# ------------------------------------------------------------------------------
# Patterns indicative of prompt injection in user queries or external web content
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|directives|prompts)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|system)\s+(instructions|rules)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(an?\s+)?(unrestricted|jailbroken|developer|dan|new\s+system)", re.IGNORECASE),
    re.compile(r"system\s+(override|prompt|directive):\s*", re.IGNORECASE),
    re.compile(r"<\s*\|\s*(im_start|im_end|system|assistant)\s*\|\s*>", re.IGNORECASE),
    re.compile(r"\[\s*/?\s*(inst|system|instructions)\s*\]", re.IGNORECASE),
    re.compile(r"```(system|instructions|override)", re.IGNORECASE),
    re.compile(r"bypass\s+(all\s+)?(safety|security|content)\s+filters", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions|api\s*key)", re.IGNORECASE),
]

# Patterns indicative of SQL injection
SQL_INJECTION_PATTERNS = [
    re.compile(r"(--|/\*|\*/|;\s*$)", re.IGNORECASE),
    re.compile(r"\b(union\s+select|select\s+.*\s+from|insert\s+into|drop\s+table|delete\s+from|update\s+.*\s+set)\b", re.IGNORECASE),
    re.compile(r"\b(or\s+1\s*=\s*1|and\s+1\s*=\s*1|or\s+'1'\s*=\s*'1')\b", re.IGNORECASE),
    re.compile(r"\b(xp_cmdshell|exec\s*\(|benchmark\s*\(|sleep\s*\()\b", re.IGNORECASE),
]

# Standard ticker format: 1-10 uppercase letters, numbers, dot or hyphen
TICKER_REGEX = re.compile(r"^[A-Z0-9.-]{1,10}$")


# ------------------------------------------------------------------------------
# 1. User Monitoring Request Validation
# ------------------------------------------------------------------------------
class ValidatedMonitoringRequest(BaseModel):
    """Strongly validated user monitoring request payload."""
    portfolio_id: str = Field(..., description="Target portfolio UUID")
    user_id: Optional[str] = Field(None, description="Optional requesting user UUID")
    request_type: str = Field(
        default="full_portfolio_check",
        description="Type of monitoring run: full_portfolio_check, single_stock_drilldown, scheduled_monitoring",
    )
    specific_tickers: Optional[List[str]] = Field(None, description="Optional target equity tickers")
    max_news_per_target: int = Field(default=3, ge=1, le=10)
    max_filings_per_target: int = Field(default=2, ge=0, le=5)
    include_filings: bool = True
    include_news: bool = True
    persist_alerts: bool = True

    @field_validator("portfolio_id")
    @classmethod
    def validate_portfolio_uuid(cls, val: str) -> str:
        s = val.strip()
        if not s:
            raise SecurityValidationError("Invalid request: portfolio_id is required and cannot be empty.")
        try:
            uuid_obj = uuid.UUID(s)
            return str(uuid_obj)
        except (ValueError, AttributeError) as exc:
            raise SecurityValidationError(f"Invalid portfolio_id format: '{s}' is not a valid UUID.") from exc

    @field_validator("user_id")
    @classmethod
    def validate_user_uuid(cls, val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        s = val.strip()
        try:
            uuid_obj = uuid.UUID(s)
            return str(uuid_obj)
        except (ValueError, AttributeError) as exc:
            raise SecurityValidationError(f"Invalid user_id format: '{s}' is not a valid UUID.") from exc

    @field_validator("request_type")
    @classmethod
    def validate_request_type(cls, val: str) -> str:
        allowed = {"full_portfolio_check", "single_stock_drilldown", "scheduled_monitoring"}
        s = val.lower().strip()
        if s not in allowed:
            raise SecurityValidationError(f"Invalid request_type '{val}'. Must be one of {allowed}.")
        return s

    @field_validator("specific_tickers")
    @classmethod
    def validate_tickers(cls, tickers: Optional[List[str]]) -> Optional[List[str]]:
        if tickers is None:
            return None
        validated: List[str] = []
        for t in tickers:
            s = t.strip().upper()
            # Check prompt injection or SQL injection in ticker parameter
            detect_prompt_injection(s, field_name="specific_tickers")
            detect_sql_injection(s, field_name="specific_tickers")
            if not TICKER_REGEX.match(s):
                raise SecurityValidationError(
                    f"Invalid ticker symbol '{t}'. Must be 1-10 uppercase alphanumeric characters (e.g., AAPL, BRK.B)."
                )
            if s not in validated:
                validated.append(s)
        return validated


def validate_monitoring_request(payload: Dict[str, Any]) -> ValidatedMonitoringRequest:
    """Validate user monitoring request against security constraints."""
    try:
        return ValidatedMonitoringRequest(**payload)
    except Exception as val_err:
        if hasattr(val_err, "errors"):
            for err in val_err.errors():
                ctx = err.get("ctx", {})
                exc = ctx.get("error") if isinstance(ctx, dict) else None
                if isinstance(exc, SecurityValidationError):
                    raise exc
        if isinstance(val_err, SecurityValidationError):
            raise val_err
        raise SecurityValidationError(str(val_err)) from val_err


# ------------------------------------------------------------------------------
# 2. Prompt & SQL Injection Detection Helpers
# ------------------------------------------------------------------------------
def detect_prompt_injection(text: str, field_name: str = "text") -> None:
    """Scan text for prompt injection signatures and raise PromptInjectionDetectedError if found."""
    if not text:
        return
    for pattern in PROMPT_INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            matched_phrase = match.group(0)
            logger.warning("Prompt injection signature detected in '%s': '%s'", field_name, matched_phrase)
            raise PromptInjectionDetectedError(
                f"Security alert: Prompt injection signature detected in {field_name} ('{matched_phrase}')."
            )


def detect_sql_injection(text: str, field_name: str = "text") -> None:
    """Scan text for SQL injection signatures and raise MaliciousInputError if found."""
    if not text:
        return
    for pattern in SQL_INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            matched_phrase = match.group(0)
            logger.warning("SQL injection signature detected in '%s': '%s'", field_name, matched_phrase)
            raise MaliciousInputError(
                f"Security alert: Potential SQL injection detected in {field_name} ('{matched_phrase}')."
            )


# ------------------------------------------------------------------------------
# 3. Untrusted External Research Sanitization
# ------------------------------------------------------------------------------
class ThreatLevel(str, Enum):
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"


class SanitizedResearchContent(BaseModel):
    """Sanitized external document content with isolated risk classification."""
    is_safe: bool
    threat_level: ThreatLevel
    sanitized_text: str
    detected_threats: List[str] = Field(default_factory=list)
    isolation_notice: Optional[str] = None


def sanitize_external_research_content(raw_content: str, max_length: int = 10000) -> SanitizedResearchContent:
    """
    Treats external research as strictly untrusted data.
    Detects and neutralizes prompt injection attempts, strip active script constructs,
    and wraps untrusted content in an explicit data boundary for LLM consumption.
    """
    if not raw_content:
        return SanitizedResearchContent(
            is_safe=True,
            threat_level=ThreatLevel.SAFE,
            sanitized_text="",
        )

    # 1. Truncate oversized raw content
    text = raw_content[:max_length]
    detected_threats: List[str] = []

    # 2. Check for prompt injection signatures in scraped webpage content
    for pattern in PROMPT_INJECTION_PATTERNS:
        matches = pattern.findall(text)
        for m in matches:
            threat_str = m[0] if isinstance(m, tuple) else m
            if threat_str and threat_str not in detected_threats:
                detected_threats.append(threat_str)

    # 3. Strip raw HTML tags / script markers if present
    cleaned_text = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", " [SCRIPT_REMOVED] ", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = re.sub(r"<\s*style[^>]*>.*?<\s*/\s*style\s*>", " [STYLE_REMOVED] ", cleaned_text, flags=re.IGNORECASE | re.DOTALL)
    cleaned_text = re.sub(r"<\s*iframe[^>]*>.*?<\s*/\s*iframe\s*>", " [IFRAME_REMOVED] ", cleaned_text, flags=re.IGNORECASE | re.DOTALL)

    # 4. Neutralize instruction override phrases by escaping delimiters
    for pattern in PROMPT_INJECTION_PATTERNS:
        cleaned_text = pattern.sub(r"[SUSPICIOUS_DIRECTIVE_MUTED: \g<0>]", cleaned_text)

    # 5. Classify threat level
    if len(detected_threats) >= 2:
        threat_level = ThreatLevel.HIGH_RISK
        is_safe = False
    elif len(detected_threats) == 1:
        threat_level = ThreatLevel.SUSPICIOUS
        is_safe = True  # Sanitized and quarantined
    else:
        threat_level = ThreatLevel.SAFE
        is_safe = True

    # 6. Apply explicit untrusted data boundary wrapper
    isolated_text = (
        f"--- BEGIN UNTRUSTED EXTERNAL DATA ---\n"
        f"{cleaned_text.strip()}\n"
        f"--- END UNTRUSTED EXTERNAL DATA ---"
    )

    isolation_notice = (
        f"Notice: External content contained {len(detected_threats)} suspicious directive(s). "
        "Directives have been neutralized and enclosed in untrusted data boundaries."
        if detected_threats else None
    )

    return SanitizedResearchContent(
        is_safe=is_safe,
        threat_level=threat_level,
        sanitized_text=isolated_text,
        detected_threats=detected_threats,
        isolation_notice=isolation_notice,
    )


# ------------------------------------------------------------------------------
# 4. MCP Tool Arguments Validation & SSRF Prevention
# ------------------------------------------------------------------------------
PRIVATE_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),    # Private RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),   # Private RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud metadata (AWS/GCP/Azure 169.254.169.254)
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]


def validate_url_safety(url: str) -> str:
    """
    Validate that target URL is HTTP/HTTPS and does not target loopback,
    private LAN, or cloud metadata services (SSRF defense).
    """
    if not url or not isinstance(url, str):
        raise SSRFAttemptError("URL must be a non-empty string.")

    cleaned_url = url.strip()
    try:
        parsed = urlparse(cleaned_url)
    except Exception as exc:
        raise SSRFAttemptError(f"Malformed URL: {exc}") from exc

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SSRFAttemptError(f"Invalid URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFAttemptError("URL is missing a valid hostname.")

    # Check for direct IP address SSRF (e.g. http://127.0.0.1 or http://169.254.169.254)
    is_ip = False
    try:
        ip_obj = ipaddress.ip_address(hostname)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        for net in PRIVATE_IP_NETWORKS:
            if ip_obj in net:
                raise SSRFAttemptError(
                    f"Blocked SSRF destination: '{hostname}' belongs to restricted network '{net}'."
                )
    else:
        # Hostname is a domain name (e.g. reuters.com), check for localhost/internal aliases
        lower_host = hostname.lower()
        if lower_host in ("localhost", "metadata.google.internal", "instance-data"):
            raise SSRFAttemptError(f"Blocked SSRF destination: '{lower_host}' is a restricted host.")

    return cleaned_url


def validate_mcp_arguments(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strictly validate tool arguments prior to dispatch to any MCP server.
    Ensures parameters adhere to schema limits and guards against SQL injection / SSRF.
    """
    if not isinstance(arguments, dict):
        raise SecurityValidationError("Tool arguments must be provided as a dictionary.")

    t_name = tool_name.strip()
    validated_args: Dict[str, Any] = dict(arguments)

    # 1. Database MCP Tools
    if t_name in ("get_portfolio", "get_holdings"):
        p_id = str(arguments.get("portfolio_id", "")).strip()
        try:
            uuid.UUID(p_id)
        except ValueError as exc:
            raise SecurityValidationError(f"Tool '{t_name}' requires a valid UUID for 'portfolio_id'.") from exc
        validated_args["portfolio_id"] = p_id

    elif t_name == "save_monitoring_alert":
        p_id = str(arguments.get("portfolio_id", "")).strip()
        try:
            uuid.UUID(p_id)
        except ValueError as exc:
            raise SecurityValidationError("save_monitoring_alert requires a valid UUID for 'portfolio_id'.") from exc

        title = str(arguments.get("title", "")).strip()
        if not title:
            raise SecurityValidationError("Alert title cannot be empty.")
        detect_sql_injection(title, field_name="title")

        severity = str(arguments.get("severity", "")).upper().strip()
        if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            raise SecurityValidationError(f"Invalid alert severity: '{severity}'.")

    elif t_name == "save_research_event":
        c_id = str(arguments.get("company_id", "")).strip()
        try:
            uuid.UUID(c_id)
        except ValueError as exc:
            raise SecurityValidationError("save_research_event requires a valid UUID for 'company_id'.") from exc

        title = str(arguments.get("title", "")).strip()
        if not title:
            raise SecurityValidationError("Research event title cannot be empty.")
        detect_sql_injection(title, field_name="title")

    # 2. Research MCP Tools
    elif t_name in ("search_company_news", "search_company_filings"):
        c_name = str(arguments.get("company_name", "")).strip()
        ticker = str(arguments.get("ticker", "")).strip().upper()
        if not c_name and not ticker:
            raise SecurityValidationError(f"Tool '{t_name}' requires company_name or ticker.")

        if ticker and not TICKER_REGEX.match(ticker):
            raise SecurityValidationError(f"Invalid ticker format: '{ticker}'.")

        detect_prompt_injection(c_name, field_name="company_name")
        detect_sql_injection(c_name, field_name="company_name")

        max_res = int(arguments.get("max_results", 5))
        validated_args["max_results"] = max(1, min(max_res, 10))

    elif t_name in ("fetch_webpage", "extract_article_content"):
        url = str(arguments.get("url", "")).strip()
        validated_args["url"] = validate_url_safety(url)

    # 3. Analysis MCP Tools
    elif t_name == "detect_duplicate_events":
        cand_title = str(arguments.get("candidate_title", "")).strip()
        if not cand_title:
            raise SecurityValidationError("detect_duplicate_events requires candidate_title.")
        detect_sql_injection(cand_title, field_name="candidate_title")

    return validated_args
