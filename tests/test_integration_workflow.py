"""
Portfolio Health Monitor – Complete Integration Workflow Tests
Tests the full autonomous monitoring lifecycle for a hypothetical portfolio:
Holdings:
  - Apple Inc. (AAPL)
  - Microsoft Corporation (MSFT)
  - NVIDIA Corporation (NVDA)

Workflow Steps Verified:
1. Retrieve portfolio metadata and active holdings from PostgreSQL via Database MCP.
2. Discover relevant news and disclosures via Research MCP (mocked external web calls).
3. Verify evidence and extract corroborated facts (mocked external LLM calls).
4. Identify affected holdings and compute evidence-supported mathematical exposure.
5. Generate structured alerts and persist them in PostgreSQL via Database MCP.
6. Return a comprehensive non-advisory monitoring report through FastAPI.
7. Retrieve persisted alerts through GET /api/v1/portfolios/{portfolio_id}/alerts.
8. Enforce user isolation and ownership boundaries across all endpoints.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch
import uuid

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.agents.verification_agent import LLMVerificationSchema
from app.core.security import create_access_token, get_password_hash
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.company import Company
from app.models.holding import Holding
from app.models.monitoring_alert import MonitoringAlert
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.llm import LLMService
from app.services.research import ResearchArticle, ResearchService


@pytest.fixture(autouse=True)
def dispose_db_pool():
    """Ensure engine pool connections do not bleed across async test event loops."""
    yield
    asyncio.run(engine.dispose())


@pytest.mark.anyio
async def test_complete_portfolio_monitoring_integration():
    """
    Full end-to-end integration test with hypothetical portfolio:
    AAPL (40%), MSFT (35%), NVDA (25%).
    Verifies DB retrieval, discovery, verification, impact, alert persistence in PostgreSQL,
    and FastAPI response delivery.
    """
    # --------------------------------------------------------------------------
    # 1. Setup Test Database Entities (User, Portfolio, Companies, Holdings)
    # --------------------------------------------------------------------------
    async with AsyncSessionLocal() as session:
        # Create Owner User
        user = User(
            email=f"investor_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=get_password_hash("securepass123"),
            full_name="Portfolio Manager One",
        )
        # Create Attacker / Other User for Isolation Testing
        other_user = User(
            email=f"attacker_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=get_password_hash("securepass123"),
            full_name="Unauthorized User",
        )
        session.add_all([user, other_user])
        await session.flush()

        user_token = create_access_token(user.id)
        other_token = create_access_token(other_user.id)

        # Create Portfolio
        portfolio = Portfolio(
            user_id=user.id,
            name=f"Tech Growth Alpha {uuid.uuid4().hex[:4]}",
            description="Hypothetical concentrated tech portfolio",
            currency="USD",
        )
        session.add(portfolio)
        await session.flush()

        # Seed or reuse 3 Target Companies: AAPL, MSFT, NVDA
        async def get_or_create_company(ticker: str, name: str, sector: str, industry: str) -> Company:
            stmt = select(Company).where(Company.ticker == ticker)
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing:
                return existing
            comp = Company(
                ticker=ticker,
                name=name,
                sector=sector,
                industry=industry,
                is_active=True,
            )
            session.add(comp)
            await session.flush()
            return comp

        company_aapl = await get_or_create_company("AAPL", "Apple Inc.", "Technology", "Consumer Electronics")
        company_msft = await get_or_create_company("MSFT", "Microsoft Corporation", "Technology", "Software - Infrastructure")
        company_nvda = await get_or_create_company("NVDA", "NVIDIA Corporation", "Technology", "Semiconductors")

        # Seed Holdings:
        # AAPL: 400 shares @ $150 = $60,000 (40.0% weight)
        # MSFT: 125 shares @ $420 = $52,500 (35.0% weight)
        # NVDA: 300 shares @ $125 = $37,500 (25.0% weight)
        # Total Portfolio Market Value = $150,000
        holding_aapl = Holding(
            portfolio_id=portfolio.id,
            company_id=company_aapl.id,
            shares=Decimal("400.000000"),
            average_buy_price=Decimal("140.0000"),
            current_price=Decimal("150.0000"),
            market_value=Decimal("60000.0000"),
            weight_pct=Decimal("40.00"),
        )
        holding_msft = Holding(
            portfolio_id=portfolio.id,
            company_id=company_msft.id,
            shares=Decimal("125.000000"),
            average_buy_price=Decimal("400.0000"),
            current_price=Decimal("420.0000"),
            market_value=Decimal("52500.0000"),
            weight_pct=Decimal("35.00"),
        )
        holding_nvda = Holding(
            portfolio_id=portfolio.id,
            company_id=company_nvda.id,
            shares=Decimal("300.000000"),
            average_buy_price=Decimal("100.0000"),
            current_price=Decimal("125.0000"),
            market_value=Decimal("37500.0000"),
            weight_pct=Decimal("25.00"),
        )
        session.add_all([holding_aapl, holding_msft, holding_nvda])
        await session.commit()

        portfolio_id_str = str(portfolio.id)
        aapl_ticker = company_aapl.ticker
        msft_ticker = company_msft.ticker
        nvda_ticker = company_nvda.ticker

    user_headers = {"Authorization": f"Bearer {user_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # --------------------------------------------------------------------------
    # 2. Configure Mocked External Services (Research Search & LLM Verification)
    # --------------------------------------------------------------------------
    run_id = uuid.uuid4().hex[:6]

    async def mock_search_company_news(company_name: str, ticker: str = None, max_results: int = 5, **kwargs):
        """Mock news search for AAPL, MSFT, and NVDA with unique titles per test execution."""
        query_target = f"{company_name} {ticker or ''}".upper()
        if "AAPL" in query_target or "APPLE" in query_target:
            content = f"Apple announces major enterprise AI initiative integrating on-device neural processing {run_id}."
            return [
                ResearchArticle(
                    title=f"Apple Expands Enterprise AI Across Next-Gen Devices {run_id}",
                    url=f"https://finance.example.com/news/apple-ai-{run_id}",
                    snippet=content,
                    extracted_content=content,
                    source_name="finance.example.com",
                    publication_date=datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc),
                    score=0.92,
                )
            ]
        elif "MSFT" in query_target or "MICROSOFT" in query_target:
            content = f"Microsoft reports quarterly cloud infrastructure growth exceeding analyst consensus by 4% {run_id}."
            return [
                ResearchArticle(
                    title=f"Microsoft Azure Cloud Infrastructure Surges {run_id}",
                    url=f"https://cloudnews.example.com/msft-cloud-{run_id}",
                    snippet=content,
                    extracted_content=content,
                    source_name="cloudnews.example.com",
                    publication_date=datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc),
                    score=0.89,
                )
            ]
        elif "NVDA" in query_target or "NVIDIA" in query_target:
            content = f"NVIDIA previews its next GPU architecture alongside regulatory compliance updates {run_id}."
            return [
                ResearchArticle(
                    title=f"NVIDIA Unveils High-Throughput Architecture Under Review {run_id}",
                    url=f"https://semiresearch.example.com/nvda-arch-{run_id}",
                    snippet=content,
                    extracted_content=content,
                    source_name="semiresearch.example.com",
                    publication_date=datetime(2026, 11, 3, 14, 0, 0, tzinfo=timezone.utc),
                    score=0.95,
                )
            ]
        return []

    async def mock_generate_structured(messages, response_model, **kwargs):
        """Mock LLM structured outputs according to the requested Pydantic schema."""
        content_str = " ".join(m.get("content", "") for m in messages)
        # Check if caller is Verification Agent (response_model == LLMVerificationSchema)
        if response_model is LLMVerificationSchema:
            if "AAPL" in content_str or "Apple" in content_str:
                return LLMVerificationSchema(
                    canonical_title=f"Apple Enterprise AI Expansion Corroborated {run_id}",
                    verified_summary="Apple launched enterprise-focused neural processing software and edge AI capabilities.",
                    event_type="PRODUCT",
                    sentiment="BULLISH",
                    verification_status="VERIFIED",
                    credibility_score=0.92,
                    facts=["Apple released enterprise AI tools", "Integration spans macOS and iOS"],
                    speculative_claims=[],
                )
            elif "MSFT" in content_str or "Microsoft" in content_str:
                return LLMVerificationSchema(
                    canonical_title=f"Microsoft Cloud Demand Exceeds Guidance {run_id}",
                    verified_summary="Azure revenue reported 4% ahead of consensus estimates driven by cloud infrastructure contracts.",
                    event_type="EARNINGS",
                    sentiment="BULLISH",
                    verification_status="VERIFIED",
                    credibility_score=0.90,
                    facts=["Azure grew 4% above consensus", "Infrastructure orders hit new records"],
                    speculative_claims=[],
                )
            else:
                return LLMVerificationSchema(
                    canonical_title=f"NVIDIA Architecture Facing Regulatory Review {run_id}",
                    verified_summary="New GPU line revealed with updated compliance safeguards for global export standards.",
                    event_type="REGULATORY",
                    sentiment="BEARISH",
                    verification_status="VERIFIED",
                    credibility_score=0.88,
                    facts=["New architecture announced", "Export compliance updates instituted"],
                    speculative_claims=["Unconfirmed estimates of secondary market shipments"],
                )
        return response_model()

    # --------------------------------------------------------------------------
    # 3. Execute Complete Workflow Through FastAPI POST /monitor
    # --------------------------------------------------------------------------
    with patch.object(ResearchService, "search_company_news", side_effect=mock_search_company_news), \
         patch.object(LLMService, "generate_structured", side_effect=mock_generate_structured):

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 3a. Verify Ownership Isolation: Unauthorized user cannot monitor
            res_unauth = await client.post(
                f"/api/v1/portfolios/{portfolio_id_str}/monitor",
                json={"include_news": True, "persist_alerts": True},
                headers=other_headers,
            )
            assert res_unauth.status_code == 404, "Other user must not access another user's portfolio"

            # 3b. Authenticated Owner triggers the autonomous monitoring workflow
            trigger_payload = {
                "specific_tickers": None,  # Monitor entire portfolio
                "max_news_per_target": 2,
                "include_news": True,
                "include_filings": False,
                "persist_alerts": True,
            }
            res_monitor = await client.post(
                f"/api/v1/portfolios/{portfolio_id_str}/monitor",
                json=trigger_payload,
                headers=user_headers,
            )
            assert res_monitor.status_code == 200, f"Monitoring failed: {res_monitor.text}"
            monitor_data = res_monitor.json()

            # Verify response schema and non-advisory compliance
            assert monitor_data["status"] == "SUCCESS"
            assert monitor_data["portfolio_id"] == portfolio_id_str
            assert monitor_data["alerts_generated_count"] >= 1
            assert monitor_data["persisted_alerts_count"] >= 1
            assert "does NOT contain investment recommendations" in monitor_data["non_advisory_notice"]
            assert "executive_summary" in monitor_data
            assert monitor_data["aggregate_risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

            # ------------------------------------------------------------------
            # 4. Verify Database Persistence of Monitoring Alerts in PostgreSQL
            # ------------------------------------------------------------------
            res_alerts = await client.get(
                f"/api/v1/portfolios/{portfolio_id_str}/alerts",
                headers=user_headers,
            )
            assert res_alerts.status_code == 200
            alerts_data = res_alerts.json()
            assert len(alerts_data) >= 1

            # Check structure of persisted alert items
            first_alert = alerts_data[0]
            assert "id" in first_alert
            assert first_alert["portfolio_id"] == portfolio_id_str
            assert first_alert["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
            assert "Impact on" in first_alert["title"]

            # ------------------------------------------------------------------
            # 5. Verify Direct PostgreSQL Persistence via SQLAlchemy
            # ------------------------------------------------------------------
            async with AsyncSessionLocal() as session:
                db_alerts_stmt = select(MonitoringAlert).where(
                    MonitoringAlert.portfolio_id == uuid.UUID(portfolio_id_str)
                )
                db_alerts = (await session.execute(db_alerts_stmt)).scalars().all()
                assert len(db_alerts) >= 1
                for alert in db_alerts:
                    assert alert.portfolio_id == uuid.UUID(portfolio_id_str)
                    assert alert.title is not None
                    assert alert.message is not None

            # ------------------------------------------------------------------
            # 6. Verify Ownership Protection on GET /alerts
            # ------------------------------------------------------------------
            res_alerts_unauth = await client.get(
                f"/api/v1/portfolios/{portfolio_id_str}/alerts",
                headers=other_headers,
            )
            assert res_alerts_unauth.status_code == 404

