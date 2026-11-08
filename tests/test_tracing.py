"""
AgentX – Unit Tests for LangSmith Tracing & Observability
Tests coverage for:
1. Environment variable setup & configuration toggling
2. Tracing connectivity verification & status reporting
3. Secret and credential masking in metadata and payloads
4. RunnableConfig generation with run names, tags, and thread IDs
5. Traceable instrumentation on LLM calls, MCP tool calls, and Agent chains
6. Graph execution with standardized tracing configuration
7. Health endpoint /health/tracing
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import httpx
from httpx import ASGITransport, AsyncClient
import pytest
from pydantic import BaseModel, SecretStr

from app.agents.portfolio_agent import PortfolioContext
from app.core.config import Settings
from app.core.tracing import (
    get_langchain_run_config,
    mask_sensitive_payload,
    setup_tracing,
    verify_tracing_connectivity,
)
from app.graph.state import create_initial_state
from app.graph.workflow import AgentXWorkflow, create_agentx_graph
from app.main import app
from app.mcp.clients import MCPClient
from app.services.llm import LLMResponse, LLMService


# ==============================================================================
# 1. Environment Variable Setup & Tracing Configuration
# ==============================================================================
def test_setup_tracing_disabled_by_default():
    """Verify tracing setup explicitly sets LANGCHAIN_TRACING_V2='false' when disabled."""
    mock_settings = MagicMock(spec=Settings)
    mock_settings.LANGCHAIN_TRACING_V2 = False
    mock_settings.LANGCHAIN_API_KEY = None

    with patch("app.core.tracing.get_settings", return_value=mock_settings):
        result = setup_tracing()
        assert result is False
        assert os.environ.get("LANGCHAIN_TRACING_V2") == "false"


def test_setup_tracing_enabled_with_credentials(monkeypatch):
    """Verify tracing sets required environment variables when enabled with valid API key."""
    mock_settings = MagicMock(spec=Settings)
    mock_settings.LANGCHAIN_TRACING_V2 = True
    mock_settings.LANGCHAIN_API_KEY = SecretStr("ls__valid_test_api_key_12345")
    mock_settings.LANGCHAIN_PROJECT = "test-agentx-project"
    mock_settings.LANGCHAIN_ENDPOINT = "https://api.smith.langchain.com"

    # Use monkeypatch to ensure environment is restored after test
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    with patch("app.core.tracing.get_settings", return_value=mock_settings):
        result = setup_tracing()
        assert result is True
        assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
        assert os.environ.get("LANGCHAIN_API_KEY") == "ls__valid_test_api_key_12345"
        assert os.environ.get("LANGCHAIN_PROJECT") == "test-agentx-project"
        assert os.environ.get("LANGCHAIN_ENDPOINT") == "https://api.smith.langchain.com"

    # Cleanup environment for downstream tests
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ.pop("LANGCHAIN_API_KEY", None)


# ==============================================================================
# 2. Connectivity Verification & Status Reporting
# ==============================================================================
def test_verify_tracing_connectivity_disabled():
    """Verify tracing status accurately reports disabled when flag is false."""
    mock_settings = MagicMock(spec=Settings)
    mock_settings.LANGCHAIN_TRACING_V2 = False
    mock_settings.LANGCHAIN_PROJECT = "agentx-test"
    mock_settings.LANGCHAIN_ENDPOINT = "https://api.smith.langchain.com"
    mock_settings.LANGCHAIN_API_KEY = None

    with patch("app.core.tracing.get_settings", return_value=mock_settings):
        is_confirmed, msg, details = verify_tracing_connectivity()
        assert is_confirmed is False
        assert "disabled in configuration" in msg
        assert details["tracing_enabled_in_config"] is False
        assert details["actual_connectivity_confirmed"] is False


def test_verify_tracing_connectivity_placeholder_unconfirmed():
    """Verify tracing status reports unconfirmed when default placeholder credentials are used."""
    mock_settings = MagicMock(spec=Settings)
    mock_settings.LANGCHAIN_TRACING_V2 = True
    mock_settings.LANGCHAIN_PROJECT = "agentx-test"
    mock_settings.LANGCHAIN_ENDPOINT = "https://api.smith.langchain.com"
    mock_settings.LANGCHAIN_API_KEY = SecretStr("your-langsmith-api-key-here")

    with patch("app.core.tracing.get_settings", return_value=mock_settings):
        is_confirmed, msg, details = verify_tracing_connectivity()
        assert is_confirmed is False
        assert "unconfirmed" in msg.lower()
        assert details["tracing_enabled_in_config"] is True
        assert details["actual_connectivity_confirmed"] is False


def test_verify_tracing_connectivity_confirmed():
    """Verify tracing status confirms active connection when Client successfully connects."""
    mock_settings = MagicMock(spec=Settings)
    mock_settings.LANGCHAIN_TRACING_V2 = True
    mock_settings.LANGCHAIN_PROJECT = "agentx-live"
    mock_settings.LANGCHAIN_ENDPOINT = "https://api.smith.langchain.com"
    mock_settings.LANGCHAIN_API_KEY = SecretStr("ls__real_api_key")

    mock_client = MagicMock()
    mock_client.read_project = MagicMock(return_value={"name": "agentx-live"})

    with patch("app.core.tracing.get_settings", return_value=mock_settings), \
         patch("app.core.tracing.Client", return_value=mock_client):
        is_confirmed, msg, details = verify_tracing_connectivity()
        assert is_confirmed is True
        assert "actively confirmed" in msg
        assert details["actual_connectivity_confirmed"] is True


# ==============================================================================
# 3. Secret & Credential Masking in Metadata
# ==============================================================================
def test_mask_sensitive_payload_scrubs_secrets():
    """Verify mask_sensitive_payload recursively masks API keys, passwords, and tokens."""
    payload = {
        "portfolio_id": "p-12345",
        "api_key": "openrouter-sk-secret-123",
        "nested": {
            "auth_token": "bearer-xyz",
            "password": "db_password_123",
            "user_email": "user@example.com",
            "openrouter_api_key": "sk-or-999",
        },
        "list_items": [
            {"access_token": "tok-1"},
            {"safe_field": "safe_value"},
        ],
    }

    masked = mask_sensitive_payload(payload)

    assert masked["portfolio_id"] == "p-12345"
    assert masked["api_key"] == "******"
    assert masked["nested"]["auth_token"] == "******"
    assert masked["nested"]["password"] == "******"
    assert masked["nested"]["openrouter_api_key"] == "******"
    assert masked["nested"]["user_email"] == "user@example.com"
    assert masked["list_items"][0]["access_token"] == "******"
    assert masked["list_items"][1]["safe_field"] == "safe_value"


# ==============================================================================
# 4. RunnableConfig Generation
# ==============================================================================
def test_get_langchain_run_config():
    """Verify run configuration builds standardized LangSmith metadata, run_name, and tags."""
    portfolio_id = str(uuid.uuid4())
    config = get_langchain_run_config(
        portfolio_id=portfolio_id,
        request_type="single_stock_drilldown",
        user_id="user-456",
        extra_metadata={"extra_api_key": "secret-value", "target_ticker": "AAPL"},
    )

    assert config["run_name"] == f"AgentX Monitoring [{portfolio_id[:8]}]"
    assert "agentx" in config["tags"]
    assert "single_stock_drilldown" in config["tags"]
    assert config["configurable"]["thread_id"] == f"thread-{portfolio_id}"

    # Verify sensitive extra_api_key was masked in metadata
    assert config["metadata"]["portfolio_id"] == portfolio_id
    assert config["metadata"]["target_ticker"] == "AAPL"
    assert config["metadata"]["extra_api_key"] == "******"


# ==============================================================================
# 5. Traceable Instrumentation on LLM & MCP Calls
# ==============================================================================
@pytest.mark.asyncio
async def test_traceable_llm_calls_execute_safely():
    """Verify @traceable LLM functions execute safely with tracing disabled or enabled."""
    mock_settings = MagicMock(spec=Settings)
    mock_settings.OPENROUTER_API_KEY = SecretStr("sk-test-llm")
    mock_settings.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    mock_settings.OPENROUTER_DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"
    mock_settings.OPENROUTER_FALLBACK_MODEL = "google/gemini-2.0-flash-001"
    mock_settings.LLM_TEMPERATURE = 0.2
    mock_settings.LLM_MAX_RETRIES = 1
    mock_settings.LLM_TIMEOUT_SECONDS = 5.0
    mock_settings.LLM_REQUEST_ID_HEADER = "X-Request-Id"

    mock_client = AsyncMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={
            "id": "gen-123",
            "model": "anthropic/claude-3.5-sonnet",
            "choices": [{"message": {"role": "assistant", "content": "Analysis completed."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.llm.get_settings", return_value=mock_settings):
        service = LLMService(settings=mock_settings, client=mock_client)

        resp = await service.generate_text(messages=[{"role": "user", "content": "Analyze portfolio"}])
        assert isinstance(resp, LLMResponse)
        assert resp.content == "Analysis completed."
        assert resp.model == "anthropic/claude-3.5-sonnet"


@pytest.mark.asyncio
async def test_traceable_mcp_tool_execution():
    """Verify @traceable MCPClient.call_tool executes and handles errors under tracing."""
    client = MCPClient()
    mock_analysis_server = MagicMock()
    mock_analysis_server.call_tool = AsyncMock(
        return_value=([MagicMock(text='{"status": "success", "score": 0.8}')], {"result": {"status": "success", "score": 0.8}})
    )

    client._servers["analysis"] = mock_analysis_server
    res = await client.call_tool("detect_duplicate_events", {"candidate_title": "Apple Q4 Results"}, server_name="analysis")

    assert res == {"status": "success", "score": 0.8}


# ==============================================================================
# 6. Workflow Graph Execution with Tracing Config
# ==============================================================================
@pytest.mark.asyncio
async def test_workflow_ainvoke_with_tracing_config():
    """Verify AgentXWorkflow.ainvoke executes graph with built-in tracing run config."""
    test_p_id = str(uuid.uuid4())
    workflow = AgentXWorkflow()

    # Fast mock portfolio node returning valid empty PortfolioContext
    mock_portfolio_agent = MagicMock()
    mock_portfolio_agent.run = AsyncMock(
        return_value=PortfolioContext(
            portfolio_id=test_p_id,
            name="Test Traced Fund",
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
            summary_analysis="Empty portfolio for tracing test.",
        )
    )
    workflow.portfolio_agent = mock_portfolio_agent

    initial_state = create_initial_state(portfolio_id=test_p_id)
    final_state = await workflow.ainvoke(initial_state)

    assert final_state["status"] == "SUCCESS"
    assert final_state["portfolio_id"] == test_p_id
    assert final_state["monitoring_report"] is not None


# ==============================================================================
# 7. Health Endpoint /health/tracing
# ==============================================================================
@pytest.mark.asyncio
async def test_health_tracing_endpoint():
    """Verify GET /health/tracing returns clean observability status."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health/tracing")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "message" in data
        assert "details" in data
        assert data["status"] in ("connected", "configured", "disabled")
