"""
AgentX – Portfolio Health Monitor
Portfolios API Endpoints
"""

from decimal import Decimal
import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.security import get_current_user
from app.database.connection import get_db
from app.graph.state import DEFAULT_NON_ADVISORY_NOTICE, create_initial_state
from app.graph.workflow import AgentXWorkflow
from app.models.holding import Holding
from app.models.monitoring_alert import MonitoringAlert
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.portfolio import (
    ErrorResponse,
    HoldingSummary,
    MonitoringAlertResponse,
    MonitoringRunResponse,
    MonitoringTriggerRequest,
    PaginatedPortfolioResponse,
    PortfolioCreate,
    PortfolioDetailResponse,
    PortfolioResponse,
)

logger = logging.getLogger("agentx.api.portfolios")
router = APIRouter(prefix="/portfolios", tags=["Portfolios"])


@router.post(
    "",
    summary="Create New Portfolio",
    description="Creates a new investment portfolio scoped strictly to the authenticated user.",
    status_code=status.HTTP_201_CREATED,
    response_model=PortfolioResponse,
    responses={
        201: {"description": "Portfolio successfully created."},
        400: {"model": ErrorResponse, "description": "Invalid input data."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        409: {"model": ErrorResponse, "description": "Portfolio with this name already exists."},
    },
)
async def create_portfolio(
    payload: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioResponse:
    """
    Creates a new portfolio record.
    Security: Derives ownership exclusively from current_user.id.
    """
    # Enforce uniqueness of portfolio name per user
    existing_stmt = select(Portfolio).where(
        Portfolio.user_id == current_user.id,
        Portfolio.name == payload.name,
    )
    existing = await db.scalar(existing_stmt)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A portfolio named '{payload.name}' already exists in your account.",
        )

    portfolio = Portfolio(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        currency=payload.currency,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)

    logger.info(
        "Created portfolio | id=%s | user_id=%s | name='%s'",
        portfolio.id,
        current_user.id,
        portfolio.name,
    )

    response = PortfolioResponse.model_validate(portfolio)
    response.holdings_count = 0
    response.total_market_value = Decimal("0.0000")
    return response


@router.get(
    "",
    summary="List User Portfolios",
    description="Returns a paginated list of portfolios belonging strictly to the authenticated user.",
    response_model=PaginatedPortfolioResponse,
    responses={
        200: {"description": "Paginated list of user portfolios."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
    },
)
async def list_portfolios(
    page: int = Query(default=1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    is_active: Optional[bool] = Query(default=None, description="Optional active status filter"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedPortfolioResponse:
    """
    Lists portfolios with pagination and summary financial metrics.
    Ownership: Filters strictly by current_user.id so no other user data is exposed.
    """
    offset = (page - 1) * page_size

    # Base query restricted to current user
    base_filter = [Portfolio.user_id == current_user.id]
    if is_active is not None:
        base_filter.append(Portfolio.is_active == is_active)

    # Count total matching portfolios
    count_stmt = select(func.count(Portfolio.id)).where(*base_filter)
    total = (await db.scalar(count_stmt)) or 0

    # Retrieve paginated items with holdings eagerly loaded
    items_stmt = (
        select(Portfolio)
        .where(*base_filter)
        .options(selectinload(Portfolio.holdings))
        .order_by(Portfolio.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(items_stmt)
    portfolios = result.scalars().all()

    items: list[PortfolioResponse] = []
    for p in portfolios:
        holdings_count = len(p.holdings)
        total_market_value = sum(
            (h.market_value for h in p.holdings if h.market_value is not None),
            Decimal("0.0000"),
        )
        item_resp = PortfolioResponse.model_validate(p)
        item_resp.holdings_count = holdings_count
        item_resp.total_market_value = total_market_value
        items.append(item_resp)

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedPortfolioResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get(
    "/{portfolio_id}",
    summary="Get Portfolio Details",
    description="Returns detailed information and active position holdings for a specific portfolio.",
    response_model=PortfolioDetailResponse,
    responses={
        200: {"description": "Detailed portfolio view."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Portfolio not found or access denied."},
    },
)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioDetailResponse:
    """
    Retrieves full portfolio details and active holdings.
    Ownership: Enforces portfolio.user_id == current_user.id.
    """
    stmt = (
        select(Portfolio)
        .options(selectinload(Portfolio.holdings).joinedload(Holding.company))
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    result = await db.execute(stmt)
    portfolio = result.scalars().first()

    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )

    holdings_summary: list[HoldingSummary] = []
    total_market_value = Decimal("0.0000")

    for h in portfolio.holdings:
        summary = HoldingSummary(
            id=h.id,
            company_id=h.company_id,
            ticker=h.company.ticker if h.company else None,
            company_name=h.company.name if h.company else None,
            shares=h.shares,
            average_buy_price=h.average_buy_price,
            current_price=h.current_price,
            market_value=h.market_value,
            weight_pct=h.weight_pct,
        )
        if h.market_value is not None:
            total_market_value += h.market_value
        holdings_summary.append(summary)

    response = PortfolioDetailResponse.model_validate(portfolio)
    response.holdings = holdings_summary
    response.holdings_count = len(holdings_summary)
    response.total_market_value = total_market_value
    return response


@router.post(
    "/{portfolio_id}/monitor",
    summary="Trigger Autonomous Portfolio Monitoring",
    description="Initiates an end-to-end multi-agent LangGraph monitoring workflow for the portfolio.",
    response_model=MonitoringRunResponse,
    responses={
        200: {"description": "Monitoring run successfully executed."},
        400: {"model": ErrorResponse, "description": "Invalid monitoring request parameters."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Portfolio not found or access denied."},
        500: {"model": ErrorResponse, "description": "Monitoring workflow execution failure."},
    },
)
async def trigger_portfolio_monitoring(
    portfolio_id: uuid.UUID,
    payload: MonitoringTriggerRequest = MonitoringTriggerRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonitoringRunResponse:
    """
    Executes the AgentX autonomous multi-agent portfolio monitoring graph:
    1. Portfolio Intelligence Agent retrieves active holdings and weights.
    2. News & Filing Discovery Agent identifies recent market events.
    3. Research Verification Agent filters noise and verifies sources.
    4. Portfolio Impact Agent calculates exposure and sentiment impact.
    5. Alert & Reporting Agent synthesizes structured alerts and persists them.
    6. Supervisor Agent produces the final non-advisory monitoring report.
    """
    # Verify portfolio ownership
    stmt = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.id,
    )
    portfolio = await db.scalar(stmt)
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found or access denied.",
        )

    logger.info(
        "Starting monitoring workflow | portfolio_id=%s | user_id=%s",
        portfolio_id,
        current_user.id,
    )

    try:
        initial_state = create_initial_state(
            portfolio_id=str(portfolio_id),
            user_id=str(current_user.id),
            specific_tickers=payload.specific_tickers,
            max_news_per_target=payload.max_news_per_target,
            max_filings_per_target=payload.max_filings_per_target,
            include_filings=payload.include_filings,
            include_news=payload.include_news,
            persist_alerts=payload.persist_alerts,
        )

        workflow = AgentXWorkflow()
        result_state = await workflow.ainvoke(initial_state)

        report_obj = result_state.get("monitoring_report")
        final_obj = result_state.get("final_output")

        report_dict = report_obj.model_dump() if hasattr(report_obj, "model_dump") else (report_obj if isinstance(report_obj, dict) else {})
        final_dict = final_obj.model_dump() if hasattr(final_obj, "model_dump") else (final_obj if isinstance(final_obj, dict) else {})

        # Extract executive summary and risk levels
        executive_summary = (
            report_dict.get("executive_summary")
            or final_dict.get("executive_summary")
            or "Autonomous portfolio monitoring completed."
        )
        aggregate_risk_level = (
            report_dict.get("aggregate_risk_level")
            or final_dict.get("aggregate_risk_level")
            or "LOW"
        )
        alerts_list = report_dict.get("alerts") or []
        persisted_count = report_dict.get("persisted_alerts_count", len(alerts_list))

        return MonitoringRunResponse(
            status=result_state.get("status", "SUCCESS"),
            portfolio_id=str(portfolio_id),
            completed_at=result_state.get("completed_at"),
            executive_summary=executive_summary,
            aggregate_risk_level=aggregate_risk_level,
            alerts_generated_count=len(alerts_list),
            persisted_alerts_count=persisted_count,
            errors=result_state.get("errors", []),
            non_advisory_notice=result_state.get("non_advisory_notice", DEFAULT_NON_ADVISORY_NOTICE),
        )
    except Exception as exc:
        logger.error("Workflow failed | portfolio_id=%s | error=%s", portfolio_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Monitoring workflow execution failed: {str(exc)}",
        )


@router.get(
    "/{portfolio_id}/alerts",
    summary="Get Persisted Monitoring Alerts",
    description="Returns persisted monitoring alerts for the specified portfolio.",
    response_model=list[MonitoringAlertResponse],
    responses={
        200: {"description": "List of monitoring alerts."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Portfolio not found or access denied."},
    },
)
async def get_portfolio_alerts(
    portfolio_id: uuid.UUID,
    severity: Optional[str] = Query(default=None, description="Filter by severity: LOW, MEDIUM, HIGH, CRITICAL"),
    limit: int = Query(default=50, ge=1, le=200, description="Max alerts to retrieve"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MonitoringAlertResponse]:
    """
    Retrieves historical and recent monitoring alerts for a given portfolio.
    Ownership: Enforces portfolio.user_id == current_user.id.
    """
    # Enforce portfolio ownership
    p_stmt = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.id,
    )
    portfolio = await db.scalar(p_stmt)
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found or access denied.",
        )

    stmt = select(MonitoringAlert).where(MonitoringAlert.portfolio_id == portfolio_id)
    if severity:
        stmt = stmt.where(MonitoringAlert.severity == severity.upper())
    stmt = stmt.order_by(MonitoringAlert.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    alerts = result.scalars().all()

    return [MonitoringAlertResponse.model_validate(a) for a in alerts]


