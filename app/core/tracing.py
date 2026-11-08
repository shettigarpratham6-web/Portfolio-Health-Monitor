"""
AgentX – Portfolio Health Monitor
LangSmith Tracing & Observability Integration
Configures LangSmith environment variables, tracks LangGraph runs, agent chains,
LLM calls, and MCP tools while masking sensitive information.
"""

import copy
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from langsmith import Client, traceable

from app.core.config import get_settings

logger = logging.getLogger("agentx.tracing")

# Sensitive key patterns to mask from trace payloads and metadata
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[-_]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"auth(orization)?", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]


def mask_sensitive_payload(data: Any, max_depth: int = 5) -> Any:
    """
    Recursively scrubs API keys, authorization tokens, secrets, and credentials
    from metadata dictionaries before emitting to LangSmith.
    """
    if max_depth <= 0 or data is None:
        return data

    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_str = str(key)
            if any(pat.search(key_str) for pat in SENSITIVE_KEY_PATTERNS):
                sanitized[key] = "******"
            else:
                sanitized[key] = mask_sensitive_payload(value, max_depth - 1)
        return sanitized

    if isinstance(data, (list, tuple)):
        return [mask_sensitive_payload(item, max_depth - 1) for item in data]

    if hasattr(data, "model_dump"):
        try:
            return mask_sensitive_payload(data.model_dump(), max_depth - 1)
        except Exception:
            return str(data)

    return data


def setup_tracing() -> bool:
    """
    Configures LangSmith tracing through environment variables as required by LangChain.
    Enables tracing when configured or explicitly disables tracing without crashing.
    """
    settings = get_settings()

    if settings.LANGCHAIN_TRACING_V2 and settings.LANGCHAIN_API_KEY:
        api_key = settings.LANGCHAIN_API_KEY.get_secret_value()
        if api_key and not api_key.startswith("your-langsmith-api-key"):
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = api_key
            os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
            os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
            logger.info(
                "LangSmith tracing enabled | project=%s | endpoint=%s",
                settings.LANGCHAIN_PROJECT,
                settings.LANGCHAIN_ENDPOINT,
            )
            return True

    # Tracing is disabled in configuration or credentials are absent
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    logger.debug("LangSmith tracing is disabled in configuration.")
    return False


def verify_tracing_connectivity() -> Tuple[bool, str, Dict[str, Any]]:
    """
    Verifies actual connectivity to the LangSmith backend using credentials.
    Returns:
        (is_confirmed, summary_status, details_dict)
    """
    settings = get_settings()
    details: Dict[str, Any] = {
        "tracing_enabled_in_config": settings.LANGCHAIN_TRACING_V2,
        "project": settings.LANGCHAIN_PROJECT,
        "endpoint": settings.LANGCHAIN_ENDPOINT,
        "has_api_key": bool(settings.LANGCHAIN_API_KEY and settings.LANGCHAIN_API_KEY.get_secret_value()),
        "actual_connectivity_confirmed": False,
    }

    if not settings.LANGCHAIN_TRACING_V2:
        return (
            False,
            "Tracing is disabled in configuration (LANGCHAIN_TRACING_V2=false).",
            details,
        )

    api_key = settings.LANGCHAIN_API_KEY.get_secret_value() if settings.LANGCHAIN_API_KEY else ""
    if not api_key or api_key.startswith("your-langsmith-api-key"):
        return (
            False,
            "Tracing is enabled in configuration but unconfirmed: valid LANGCHAIN_API_KEY credentials are not available.",
            details,
        )

    # Test actual connectivity via LangSmith Client
    try:
        client = Client(
            api_url=settings.LANGCHAIN_ENDPOINT,
            api_key=api_key,
            timeout_ms=3000,
        )
        # Authenticate credentials with LangSmith endpoint
        list(client.list_projects(limit=1))
        details["actual_connectivity_confirmed"] = True
        return (
            True,
            f"LangSmith tracing actively confirmed and authenticated for project '{settings.LANGCHAIN_PROJECT}'.",
            details,
        )
    except Exception as exc:
        details["error"] = str(exc)
        return (
            False,
            f"Tracing configured but connection to LangSmith could not be confirmed: {exc}",
            details,
        )


def get_langchain_run_config(
    portfolio_id: str,
    request_type: str = "full_portfolio_check",
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Constructs a standardized, safe LangGraph/LangChain RunnableConfig
    with contextual run names, tags, and sanitized metadata.
    """
    raw_meta = {
        "portfolio_id": portfolio_id,
        "request_type": request_type,
        "user_id": user_id or "system",
        **(extra_metadata or {}),
    }

    sanitized_meta = mask_sensitive_payload(raw_meta)

    return {
        "run_name": f"AgentX Monitoring [{portfolio_id[:8]}]",
        "tags": ["agentx", "portfolio_monitoring", request_type],
        "metadata": sanitized_meta,
        "configurable": {
            "thread_id": thread_id or f"thread-{portfolio_id}",
        },
    }


__all__ = [
    "traceable",
    "setup_tracing",
    "verify_tracing_connectivity",
    "get_langchain_run_config",
    "mask_sensitive_payload",
]

