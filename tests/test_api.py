"""
Portfolio Health Monitor – Portfolio Health Monitor
API Integration Tests
"""

import asyncio
from decimal import Decimal
import uuid

from httpx import ASGITransport, AsyncClient
import pytest

from app.core.security import create_access_token, get_password_hash
from app.database import AsyncSessionLocal, engine
from app.main import app
from app.models.company import Company
from app.models.holding import Holding
from app.models.monitoring_alert import AlertSeverity, AlertStatus, AlertType, MonitoringAlert
from app.models.portfolio import Portfolio
from app.models.user import User


@pytest.fixture(autouse=True)
def dispose_db_pool():
    """Ensure engine pool connections do not bleed across async test event loops."""
    yield
    asyncio.run(engine.dispose())


@pytest.mark.anyio
async def test_health_endpoints():
    """Verify GET /health and GET /health/database."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. GET /health
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        data_health = res_health.json()
        assert data_health["status"] == "healthy"
        assert "version" in data_health

        # 2. GET /health/database
        res_db = await client.get("/health/database")
        assert res_db.status_code == 200
        data_db = res_db.json()
        assert data_db["connected"] is True
        assert data_db["database"] == "postgresql"
        assert "latency_ms" in data_db


@pytest.mark.anyio
async def test_portfolio_lifecycle_and_ownership():
    """
    Verify portfolio creation, listing, pagination, details,
    and strict isolation/ownership enforcement between distinct users.
    """
    async with AsyncSessionLocal() as session:
        # Create two test users
        user_a = User(
            email=f"usera_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="User Alpha",
        )
        user_b = User(
            email=f"userb_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="User Beta",
        )
        session.add_all([user_a, user_b])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)

        token_a = create_access_token(user_a.id)
        token_b = create_access_token(user_b.id)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. POST /api/v1/portfolios (User A creates a portfolio)
        payload = {
            "name": f"Alpha Strategy {uuid.uuid4().hex[:4]}",
            "description": "High beta tech portfolio",
            "currency": "USD",
        }
        res_create = await client.post(
            "/api/v1/portfolios", json=payload, headers=headers_a
        )
        assert res_create.status_code == 201
        portfolio_a = res_create.json()
        portfolio_a_id = portfolio_a["id"]
        assert portfolio_a["user_id"] == str(user_a.id)

        # 2. Duplicate portfolio name rejection for the same user (409 Conflict)
        res_dup = await client.post(
            "/api/v1/portfolios", json=payload, headers=headers_a
        )
        assert res_dup.status_code == 409
        assert "already exists" in res_dup.json()["detail"]

        # 3. User B can create a portfolio with the SAME name without conflict
        res_b_create = await client.post(
            "/api/v1/portfolios", json=payload, headers=headers_b
        )
        assert res_b_create.status_code == 201
        assert res_b_create.json()["user_id"] == str(user_b.id)

        # 4. GET /api/v1/portfolios (Pagination & isolation for User A)
        await client.post(
            "/api/v1/portfolios",
            json={"name": f"Alpha Income {uuid.uuid4().hex[:4]}", "currency": "USD"},
            headers=headers_a,
        )

        res_list_a = await client.get(
            "/api/v1/portfolios?page=1&page_size=10", headers=headers_a
        )
        assert res_list_a.status_code == 200
        list_data_a = res_list_a.json()
        assert list_data_a["total"] == 2
        assert len(list_data_a["items"]) == 2
        assert all(item["user_id"] == str(user_a.id) for item in list_data_a["items"])

        # 5. User B listing only returns User B's portfolio
        res_list_b = await client.get(
            "/api/v1/portfolios", headers=headers_b
        )
        assert res_list_b.status_code == 200
        list_data_b = res_list_b.json()
        assert list_data_b["total"] == 1
        assert list_data_b["items"][0]["user_id"] == str(user_b.id)

        # 6. Security Check: User B attempts to access User A's portfolio (404 Not Found)
        res_forbidden = await client.get(
            f"/api/v1/portfolios/{portfolio_a_id}", headers=headers_b
        )
        assert res_forbidden.status_code == 404

        # 7. Security Check: Client-supplied user_id injection is rejected
        res_inject = await client.post(
            "/api/v1/portfolios",
            json={
                "name": "Injected Portfolio",
                "currency": "USD",
                "user_id": str(user_b.id),
            },
            headers=headers_a,
        )
        assert res_inject.status_code == 422

        # 8. GET /api/v1/portfolios/{portfolio_id} with Holdings
        async with AsyncSessionLocal() as session:
            company = Company(
                ticker=f"AAPL_{uuid.uuid4().hex[:4]}",
                name="Apple Inc",
                sector="Technology",
            )
            session.add(company)
            await session.flush()

            holding = Holding(
                portfolio_id=uuid.UUID(portfolio_a_id),
                company_id=company.id,
                shares=Decimal("50.000000"),
                average_buy_price=Decimal("180.5000"),
                current_price=Decimal("220.0000"),
                market_value=Decimal("11000.0000"),
            )
            session.add(holding)
            await session.commit()

        res_detail = await client.get(
            f"/api/v1/portfolios/{portfolio_a_id}", headers=headers_a
        )
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["id"] == portfolio_a_id
        assert detail_data["holdings_count"] == 1
        assert float(detail_data["total_market_value"]) == 11000.0000
        assert len(detail_data["holdings"]) == 1
        assert detail_data["holdings"][0]["shares"] == "50.000000"
        assert detail_data["holdings"][0]["company_name"] == "Apple Inc"

        # 9. POST /api/v1/portfolios/{portfolio_id}/holdings (Dynamic position creation)
        res_add_holding = await client.post(
            f"/api/v1/portfolios/{portfolio_a_id}/holdings",
            headers=headers_a,
            json={
                "ticker": "NVDA",
                "company_name": "NVIDIA Corporation",
                "shares": 100,
                "average_buy_price": 125.50,
                "current_price": 140.00,
            },
        )
        assert res_add_holding.status_code == 201
        holding_added = res_add_holding.json()
        assert holding_added["ticker"] == "NVDA"
        assert float(holding_added["shares"]) == 100.0
        assert holding_added["short_id"].startswith("hold_")
        new_holding_id = holding_added["id"]

        # 10. DELETE /api/v1/portfolios/{portfolio_id}/holdings/{holding_id}
        res_del_holding = await client.delete(
            f"/api/v1/portfolios/{portfolio_a_id}/holdings/{new_holding_id}",
            headers=headers_a,
        )
        assert res_del_holding.status_code == 200
        assert res_del_holding.json()["status"] == "success"

        # 11. PATCH /api/v1/portfolios/{portfolio_id}/alerts/{alert_id} (Alert status update)
        async with AsyncSessionLocal() as session:
            alert = MonitoringAlert(
                portfolio_id=uuid.UUID(portfolio_a_id),
                title="Test Risk Event",
                message="Testing alert lifecycle transition",
                alert_type=AlertType.PORTFOLIO_RISK,
                severity=AlertSeverity.HIGH,
                status=AlertStatus.ACTIVE,
            )
            session.add(alert)
            await session.commit()
            await session.refresh(alert)
            alert_id = str(alert.id)

        res_patch_alert = await client.patch(
            f"/api/v1/portfolios/{portfolio_a_id}/alerts/{alert_id}",
            headers=headers_a,
            json={"status": "ACKNOWLEDGED"},
        )
        assert res_patch_alert.status_code == 200
        assert res_patch_alert.json()["status"] == "ACKNOWLEDGED"
        assert res_patch_alert.json()["acknowledged_at"] is not None

        # 12. POST /api/v1/portfolios/{portfolio_id}/chat (Interactive AI Copilot Q&A)
        res_chat = await client.post(
            f"/api/v1/portfolios/{portfolio_a_id}/chat",
            headers=headers_a,
            json={"query": "What are the active risk alerts for this portfolio?"},
        )
        assert res_chat.status_code == 200
        chat_data = res_chat.json()
        assert chat_data["portfolio_id"] == portfolio_a_id
        assert "answer" in chat_data
        assert len(chat_data["answer"]) > 0
        assert "non_advisory_notice" in chat_data
