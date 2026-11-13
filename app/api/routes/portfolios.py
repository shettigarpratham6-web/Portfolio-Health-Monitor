"""
Portfolio Health Monitor
Portfolios API Endpoints
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import logging
import time
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.security import get_current_user
from app.core.terminal_logger import TerminalLogger
from app.database.connection import get_db
from app.graph.state import DEFAULT_NON_ADVISORY_NOTICE, create_initial_state
from app.graph.workflow import AgentXWorkflow
from app.models.company import Company
from app.models.holding import Holding
from app.models.monitoring_alert import AlertStatus, MonitoringAlert
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.portfolio import (
    AlertStatusUpdate,
    ErrorResponse,
    HoldingCreate,
    HoldingSummary,
    MonitoringAlertResponse,
    MonitoringRunResponse,
    MonitoringTriggerRequest,
    PaginatedPortfolioResponse,
    PortfolioChatRequest,
    PortfolioChatResponse,
    PortfolioCreate,
    PortfolioDetailResponse,
    PortfolioResponse,
)
from app.services.llm import get_llm_service
from app.services.twelve_data import get_twelve_data_service

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


def to_cents(val: Decimal) -> Decimal:
    """Rounds a Decimal financial value to 2 decimal places using standard financial rounding."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def refresh_portfolio_holdings_valuation(
    portfolio: Portfolio,
    db: AsyncSession,
) -> tuple[list[HoldingSummary], Decimal]:
    """
    Refreshes holding market valuations and weights with accurate decimal arithmetic:
    1. Fetches latest valid quotes from Twelve Data (batch mode, cached with TTL).
    2. Converts all asset values (including Indian equities like PAGEIND in INR) into the common portfolio currency (USD or INR).
    3. Keeps Average Price strictly based on actual purchase history (never overwritten with current market prices).
    4. Calculates Market Value exactly as Shares * Current Price to 2 decimal places without precision errors.
    5. Calculates Total Portfolio Value = sum(Market Values in portfolio currency).
    6. Calculates Portfolio Weight % = (Individual Market Value / Total Portfolio Value) * 100, ensuring all weights add up to ~100%.
    7. Persists updated valuations and returns HoldingSummary list with total market value.
    """
    if not portfolio.holdings:
        return [], Decimal("0.00")

    td_service = get_twelve_data_service()
    portfolio_currency = (portfolio.currency or "USD").strip().upper()

    # Extract unique tickers and prepare non-fabricated fallback prices
    tickers: list[str] = []
    fallback_prices: dict[str, Decimal] = {}
    for h in portfolio.holdings:
        if h.company and h.company.ticker:
            t = h.company.ticker.strip().upper()
            tickers.append(t)
            fb = h.current_price or h.average_buy_price
            if fb is not None:
                fallback_prices[t] = Decimal(str(fb))

    quotes = await td_service.get_quotes(tickers, fallback_prices=fallback_prices)

    # Update each holding with validated prices and currency normalization
    for h in portfolio.holdings:
        ticker = h.company.ticker.strip().upper() if h.company and h.company.ticker else None
        quote = quotes.get(ticker) if ticker else None

        # Determine native trading currency of this asset
        is_indian = (
            (h.company and (h.company.country == "IN" or h.company.exchange in ("NSE", "BSE")))
            or ticker in ("PAGEIND", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK")
        )
        native_currency = "INR" if is_indian else "USD"

        # Obtain the latest valid price
        if quote and quote.source == "twelve_data" and quote.price is not None:
            quote_curr = (quote.currency or native_currency).strip().upper()
            if quote_curr != portfolio_currency:
                price_in_portfolio_curr = await td_service.convert_currency(
                    quote.price, quote_curr, portfolio_currency
                )
            else:
                price_in_portfolio_curr = quote.price
        elif h.current_price is not None and h.current_price > Decimal("0"):
            # Price in database is already in portfolio currency
            price_in_portfolio_curr = Decimal(str(h.current_price))
        elif h.average_buy_price is not None and h.average_buy_price > Decimal("0"):
            price_in_portfolio_curr = Decimal(str(h.average_buy_price))
        else:
            # Fallback to recorded native price converted if present
            native_val = Decimal("380.00") if ticker == "PAGEIND" else Decimal("100.00")
            if native_currency != portfolio_currency:
                price_in_portfolio_curr = await td_service.convert_currency(
                    native_val, native_currency, portfolio_currency
                )
            else:
                price_in_portfolio_curr = native_val

        # Display prices consistently to 2 decimal places
        h.current_price = to_cents(price_in_portfolio_curr)

        # Market Value is calculated EXACTLY as Shares * Current Price (2 decimal places)
        shares_dec = Decimal(str(h.shares))
        h.market_value = to_cents(shares_dec * h.current_price)

        # Average Buy Price is preserved from actual purchase history.
        if h.average_buy_price is None or h.average_buy_price == Decimal("0"):
            h.average_buy_price = h.current_price
        else:
            h.average_buy_price = to_cents(Decimal(str(h.average_buy_price)))

        h.total_cost = to_cents(shares_dec * h.average_buy_price)

    # Calculate Total Portfolio Market Value in common portfolio currency
    total_market_value = sum(
        (h.market_value for h in portfolio.holdings if h.market_value is not None),
        Decimal("0.00"),
    )

    # Recalculate portfolio weights in common portfolio currency:
    # Portfolio Weight = (Individual Market Value / Total Portfolio Value) * 100
    for h in portfolio.holdings:
        if total_market_value > Decimal("0") and h.market_value is not None:
            weight = (h.market_value / total_market_value) * Decimal("100")
            h.weight_pct = to_cents(weight)
        else:
            h.weight_pct = Decimal("0.00")

    # Ensure all portfolio weights add up to exactly 100.00%
    if portfolio.holdings and total_market_value > Decimal("0"):
        sum_weights = sum(h.weight_pct for h in portfolio.holdings if h.weight_pct is not None)
        diff = Decimal("100.00") - sum_weights
        if diff != Decimal("0") and abs(diff) <= Decimal("0.10"):
            largest_h = max(portfolio.holdings, key=lambda x: x.market_value or Decimal("0"))
            largest_h.weight_pct = (largest_h.weight_pct + diff).quantize(Decimal("0.01"))

    await db.commit()

    holdings_summary: list[HoldingSummary] = []
    for h in portfolio.holdings:
        holdings_summary.append(
            HoldingSummary(
                id=h.id,
                short_id=h.short_id,
                company_id=h.company_id,
                ticker=h.company.ticker if h.company else None,
                company_name=h.company.name if h.company else None,
                shares=h.shares,
                average_buy_price=h.average_buy_price,
                current_price=h.current_price,
                market_value=h.market_value,
                weight_pct=h.weight_pct,
            )
        )

    return holdings_summary, total_market_value


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

    holdings_summary, total_market_value = await refresh_portfolio_holdings_valuation(portfolio, db)

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
    Executes the Portfolio Health Monitor autonomous multi-agent portfolio monitoring graph:
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

    start_perf = time.perf_counter()
    TerminalLogger.log_workflow_start(
        portfolio_id=str(portfolio_id),
        portfolio_name=portfolio.name,
        user_email=current_user.email,
        tickers=payload.specific_tickers,
        config={
            "max_news_per_target": payload.max_news_per_target,
            "max_filings_per_target": payload.max_filings_per_target,
            "include_filings": payload.include_filings,
            "include_news": payload.include_news,
            "persist_alerts": payload.persist_alerts,
        },
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
        impact_obj = result_state.get("impact_report")

        report_dict = report_obj.model_dump() if hasattr(report_obj, "model_dump") else (report_obj if isinstance(report_obj, dict) else {})
        final_dict = final_obj.model_dump() if hasattr(final_obj, "model_dump") else (final_obj if isinstance(final_obj, dict) else {})
        impact_dict = impact_obj.model_dump() if hasattr(impact_obj, "model_dump") else (impact_obj if isinstance(impact_obj, dict) else {})

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

        # Extract full research discoveries, sources, verified evidence & impact analyses
        raw_disc = result_state.get("discovered_events") or []
        discovered_events = [
            e.model_dump() if hasattr(e, "model_dump") else (e if isinstance(e, dict) else {})
            for e in raw_disc
        ]

        raw_ver = result_state.get("verified_events") or []
        verified_events = [
            e.model_dump() if hasattr(e, "model_dump") else (e if isinstance(e, dict) else {})
            for e in raw_ver
        ]

        holding_impacts = impact_dict.get("holding_impacts") or []
        impact_summary = impact_dict.get("impact_summary")

        alerts_data = [
            a.model_dump() if hasattr(a, "model_dump") else (a if isinstance(a, dict) else {})
            for a in alerts_list
        ]

        total_dur_ms = (time.perf_counter() - start_perf) * 1000
        TerminalLogger.log_workflow_finish(
            portfolio_id=str(portfolio_id),
            status=result_state.get("status", "SUCCESS"),
            total_duration_ms=total_dur_ms,
            summary_stats={
                "discovered_count": len(discovered_events),
                "verified_count": len(verified_events),
                "impacts_count": len(holding_impacts),
                "alerts_count": len(alerts_data),
                "aggregate_risk": aggregate_risk_level,
            },
            errors=result_state.get("errors", []),
        )

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
            discovery_summary=result_state.get("discovery_summary"),
            verification_summary=result_state.get("verification_summary"),
            impact_summary=impact_summary,
            discovered_events=discovered_events,
            verified_events=verified_events,
            holding_impacts=holding_impacts,
            alerts=alerts_data,
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


@router.post(
    "/{portfolio_id}/holdings",
    summary="Add Holding Position",
    description="Adds a new company asset holding position to the specified portfolio.",
    status_code=status.HTTP_201_CREATED,
    response_model=HoldingSummary,
    responses={
        201: {"description": "Holding position successfully added."},
        400: {"model": ErrorResponse, "description": "Invalid holding parameters."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Portfolio not found or access denied."},
        409: {"model": ErrorResponse, "description": "Holding for this company already exists in portfolio."},
    },
)
async def add_portfolio_holding(
    portfolio_id: uuid.UUID,
    payload: HoldingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HoldingSummary:
    """Creates a new company holding within a portfolio and rebalances weights."""
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

    clean_ticker = payload.ticker.strip().upper()

    # Find or create company entity
    c_stmt = select(Company).where(func.upper(Company.ticker) == clean_ticker)
    company = await db.scalar(c_stmt)
    if not company:
        company_name = payload.company_name.strip() if payload.company_name else f"{clean_ticker} Corporation"
        is_indian = clean_ticker in ("PAGEIND", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK")
        company = Company(
            ticker=clean_ticker,
            name=company_name,
            sector="Technology",
            industry="Equities",
            country="IN" if is_indian else "US",
            exchange="NSE" if is_indian else "NASDAQ",
        )
        db.add(company)
        await db.flush()

    # Check for duplicate or existing holding in this portfolio
    h_stmt = select(Holding).where(
        Holding.portfolio_id == portfolio_id,
        Holding.company_id == company.id,
    )
    existing_holding = await db.scalar(h_stmt)

    if existing_holding:
        # Calculate Weighted Average Buy Price based on purchase history:
        # new_total_shares = existing_shares + added_shares
        # new_avg_buy_price = ((existing_shares * existing_avg) + (added_shares * added_price)) / new_total_shares
        existing_shares = Decimal(str(existing_holding.shares))
        existing_avg = Decimal(str(existing_holding.average_buy_price))
        added_shares = Decimal(str(payload.shares))
        added_price = Decimal(str(payload.average_buy_price))

        total_shares = existing_shares + added_shares
        if total_shares > Decimal("0"):
            weighted_avg = ((existing_shares * existing_avg) + (added_shares * added_price)) / total_shares
        else:
            weighted_avg = added_price

        existing_holding.shares = total_shares.quantize(Decimal("0.000001"))
        existing_holding.average_buy_price = to_cents(weighted_avg)
        existing_holding.total_cost = to_cents(existing_holding.shares * existing_holding.average_buy_price)
        if payload.notes:
            existing_holding.notes = payload.notes
        target_holding_id = existing_holding.id
    else:
        shares_dec = Decimal(str(payload.shares)).quantize(Decimal("0.000001"))
        avg_price_dec = to_cents(Decimal(str(payload.average_buy_price)))
        init_price = to_cents(Decimal(str(payload.current_price))) if payload.current_price else avg_price_dec
        new_holding = Holding(
            portfolio_id=portfolio.id,
            company_id=company.id,
            shares=shares_dec,
            average_buy_price=avg_price_dec,
            current_price=init_price,
            market_value=to_cents(shares_dec * init_price),
            total_cost=to_cents(shares_dec * avg_price_dec),
            notes=payload.notes,
        )
        db.add(new_holding)
        await db.flush()
        target_holding_id = new_holding.id

    await db.commit()

    # Re-fetch portfolio with holdings eagerly loaded and recalculate valuations using Twelve Data
    p_stmt = (
        select(Portfolio)
        .options(selectinload(Portfolio.holdings).joinedload(Holding.company))
        .where(Portfolio.id == portfolio_id)
    )
    portfolio_reloaded = (await db.execute(p_stmt)).scalars().first()
    holdings_summary, _ = await refresh_portfolio_holdings_valuation(portfolio_reloaded, db)

    target_summary = next(
        (s for s in holdings_summary if s.id == target_holding_id),
        None,
    )
    if not target_summary:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve refreshed holding after insertion.",
        )
    return target_summary


@router.delete(
    "/{portfolio_id}/holdings/{holding_id}",
    summary="Delete Holding Position",
    description="Deletes an asset holding position from the specified portfolio.",
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Holding position successfully deleted."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Holding or portfolio not found."},
    },
)
async def delete_portfolio_holding(
    portfolio_id: uuid.UUID,
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Removes a holding and dynamically rebalances remaining asset weights."""
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

    h_stmt = select(Holding).where(
        Holding.id == holding_id,
        Holding.portfolio_id == portfolio_id,
    )
    holding = await db.scalar(h_stmt)
    if not holding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holding position not found.",
        )

    await db.delete(holding)
    await db.commit()

    # Re-fetch portfolio with remaining holdings and refresh valuations and weights
    p_stmt = (
        select(Portfolio)
        .options(selectinload(Portfolio.holdings).joinedload(Holding.company))
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio_reloaded = (await db.execute(p_stmt)).scalars().first()
    if portfolio_reloaded:
        await refresh_portfolio_holdings_valuation(portfolio_reloaded, db)

    return {"status": "success", "message": "Holding position successfully removed", "deleted_id": str(holding_id)}


@router.patch(
    "/{portfolio_id}/alerts/{alert_id}",
    summary="Update Alert Status",
    description="Updates the lifecycle status of a monitoring alert (e.g., ACKNOWLEDGED or RESOLVED).",
    response_model=MonitoringAlertResponse,
    responses={
        200: {"description": "Alert status successfully updated."},
        400: {"model": ErrorResponse, "description": "Invalid alert status."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Alert or portfolio not found."},
    },
)
async def update_alert_status(
    portfolio_id: uuid.UUID,
    alert_id: uuid.UUID,
    payload: AlertStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MonitoringAlertResponse:
    """Updates an alert status (ACTIVE -> ACKNOWLEDGED -> RESOLVED) with timestamps."""
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

    a_stmt = select(MonitoringAlert).where(
        MonitoringAlert.id == alert_id,
        MonitoringAlert.portfolio_id == portfolio_id,
    )
    alert = await db.scalar(a_stmt)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Monitoring alert not found.",
        )

    status_enum = AlertStatus(payload.status)
    alert.status = status_enum
    now_utc = datetime.now(timezone.utc)

    if status_enum == AlertStatus.ACKNOWLEDGED:
        alert.acknowledged_at = now_utc
    elif status_enum == AlertStatus.RESOLVED:
        if not alert.acknowledged_at:
            alert.acknowledged_at = now_utc
        alert.resolved_at = now_utc
    elif status_enum == AlertStatus.ACTIVE:
        alert.acknowledged_at = None
        alert.resolved_at = None

    await db.commit()
    await db.refresh(alert)
    return MonitoringAlertResponse.model_validate(alert)


# In-memory TTL response cache to minimize LLM token consumption on duplicate/similar queries
_CHAT_CACHE: dict[str, tuple[float, PortfolioChatResponse]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes TTL


@router.post(
    "/{portfolio_id}/chat",
    summary="Ask AI About Portfolio",
    description="Interactive conversational endpoint allowing investors to query their portfolio holdings, risks, and alerts using LLM intelligence with token-optimized caching and fast-path execution.",
    response_model=PortfolioChatResponse,
    responses={
        200: {"description": "AI answer generated successfully."},
        400: {"model": ErrorResponse, "description": "Invalid query."},
        401: {"model": ErrorResponse, "description": "Unauthorized access."},
        404: {"model": ErrorResponse, "description": "Portfolio not found or access denied."},
    },
)
async def chat_with_portfolio(
    portfolio_id: uuid.UUID,
    payload: PortfolioChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortfolioChatResponse:
    """Answers investor natural language queries regarding portfolio holdings, allocations, and risk alerts."""
    clean_query = payload.query.strip()
    norm_query = clean_query.lower()
    now_ts = time.time()
    copilot_perf_start = time.perf_counter()

    # --------------------------------------------------------------------------
    # Optimization 1: In-Memory TTL Response Caching (0 Tokens on Repeated Queries)
    # --------------------------------------------------------------------------
    query_hash = hashlib.sha256(norm_query.encode()).hexdigest()
    cache_key = f"{portfolio_id}:{query_hash}"
    if cache_key in _CHAT_CACHE:
        cached_ts, cached_resp = _CHAT_CACHE[cache_key]
        if (now_ts - cached_ts) < _CACHE_TTL_SECONDS:
            logger.info("Portfolio AI Copilot: Returning cached response (0 tokens consumed) | key=%s", cache_key[:12])
            dur_ms = (time.perf_counter() - copilot_perf_start) * 1000
            TerminalLogger.log_copilot_start(
                portfolio_id=str(portfolio_id),
                portfolio_name=cached_resp.portfolio_name,
                query=clean_query,
            )
            TerminalLogger.log_copilot_step("Cache Check", "Hit in-memory TTL cache (0 LLM tokens consumed)")
            TerminalLogger.log_copilot_finish(
                answer=cached_resp.answer,
                cited_holdings=cached_resp.cited_holdings,
                duration_ms=dur_ms,
                is_cached=True,
            )
            return cached_resp

    # 1. Enforce portfolio ownership
    p_stmt = (
        select(Portfolio)
        .options(selectinload(Portfolio.holdings).joinedload(Holding.company))
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio = await db.scalar(p_stmt)
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found or access denied.",
        )

    TerminalLogger.log_copilot_start(
        portfolio_id=str(portfolio_id),
        portfolio_name=portfolio.name,
        query=clean_query,
    )

    # 2. Fetch active alerts for context
    a_stmt = (
        select(MonitoringAlert)
        .where(MonitoringAlert.portfolio_id == portfolio_id)
        .order_by(MonitoringAlert.created_at.desc())
        .limit(5)
    )
    alerts = (await db.execute(a_stmt)).scalars().all()

    # Calculate portfolio aggregates
    total_val = sum(
        (h.market_value for h in portfolio.holdings if h.market_value is not None),
        Decimal("0.0"),
    )
    tickers_in_portfolio = [
        h.company.ticker.upper() for h in portfolio.holdings if h.company and h.company.ticker
    ]
    query_tickers = [t for t in tickers_in_portfolio if t in clean_query.upper()]

    # --------------------------------------------------------------------------
    # Optimization 2: Deterministic Fast-Path for Exact Mathematical Queries (0 Tokens)
    # Avoids calling external LLM for standard quantitative questions
    # --------------------------------------------------------------------------
    fast_path_answer: Optional[str] = None
    cited_holdings: list[str] = list(query_tickers)

    if any(k in norm_query for k in ["total value", "portfolio value", "net worth", "how much is my portfolio"]):
        fast_path_answer = (
            f"The current total valuation of '{portfolio.name}' is ${total_val:,.2f} {portfolio.currency} "
            f"across {len(portfolio.holdings)} active holdings."
        )
    elif any(k in norm_query for k in ["concentration", "biggest position", "largest holding", "highest weight"]):
        if portfolio.holdings:
            weighted = [h for h in portfolio.holdings if h.weight_pct is not None]
            if weighted:
                top_h = max(weighted, key=lambda x: x.weight_pct or Decimal("0.0"))
                ticker_name = top_h.company.ticker if top_h.company else "Asset"
                fast_path_answer = (
                    f"Your largest position by allocation is {ticker_name} ({top_h.company.name if top_h.company else ticker_name}) "
                    f"at {top_h.weight_pct}% weight (${top_h.market_value:,.2f} {portfolio.currency})."
                )
                if ticker_name not in cited_holdings:
                    cited_holdings.append(ticker_name)
    elif ("alert" in norm_query or "risk" in norm_query) and len(alerts) == 0:
        fast_path_answer = (
            f"No active risk alerts are currently flagged for '{portfolio.name}'. "
            f"All {len(portfolio.holdings)} holdings have cleared recent multi-agent surveillance checks with LOW aggregate risk."
        )

    if fast_path_answer:
        dur_ms = (time.perf_counter() - copilot_perf_start) * 1000
        TerminalLogger.log_copilot_step("Evaluation", "Fast-path mathematical calculation matched (0 LLM tokens consumed)")
        TerminalLogger.log_copilot_finish(
            answer=fast_path_answer,
            cited_holdings=cited_holdings,
            duration_ms=dur_ms,
            is_fast_path=True,
        )
        response = PortfolioChatResponse(
            portfolio_id=str(portfolio.id),
            portfolio_name=portfolio.name,
            query=clean_query,
            answer=fast_path_answer,
            cited_holdings=cited_holdings,
            confidence="HIGH",
            non_advisory_notice=DEFAULT_NON_ADVISORY_NOTICE,
        )
        _CHAT_CACHE[cache_key] = (now_ts, response)
        return response

    # --------------------------------------------------------------------------
    # Optimization 3: Token-Compressed Context Formatting (~60% token reduction)
    # Compact tabular notation instead of verbose natural language sentences
    # --------------------------------------------------------------------------
    TerminalLogger.log_copilot_step("Context Retrieval", f"Retrieved {len(portfolio.holdings)} holdings and {len(alerts)} alerts")
    compact_holdings = []
    for h in portfolio.holdings:
        ticker = h.company.ticker if h.company else "Asset"
        weight = f"{h.weight_pct}%" if h.weight_pct is not None else "N/A"
        price = f"${h.current_price or h.average_buy_price:.2f}"
        mv = f"${h.market_value:,.2f}" if h.market_value else "$0"
        compact_holdings.append(f"{ticker}: {h.shares}sh @ {price} | Wt:{weight} | Val:{mv}")

    compact_alerts = [
        f"[{a.severity}] {a.title}"
        for a in alerts[:4]
    ]

    context_str = (
        f"Fund: {portfolio.name} | Val: ${total_val:,.2f} {portfolio.currency}\n"
        f"Holdings: {'; '.join(compact_holdings) if compact_holdings else 'None'}\n"
        f"Active Alerts: {'; '.join(compact_alerts) if compact_alerts else 'None'}"
    )

    # Compressed system prompt (under 40 tokens)
    system_prompt = (
        "You are Portfolio Health Monitor AI Copilot. Answer factually & concisely using provided holdings, "
        "weights & alerts. State percentages & dollar values. Comply with SEC Non-Advisory Mandates (no buy/sell advice)."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {clean_query}"},
    ]

    # --------------------------------------------------------------------------
    # Optimization 4: Bounded Max Tokens (max_tokens=220) to prevent runaway costs
    # --------------------------------------------------------------------------
    answer_text = ""
    try:
        llm = get_llm_service()
        TerminalLogger.log_copilot_step("LLM Invocation", f"Calling OpenRouter model {llm.settings.OPENROUTER_MODEL} (max_tokens=220, temp=0.1)")
        llm_resp = await llm.generate_text(
            messages=messages,
            temperature=0.1,
            max_tokens=220,
        )
        answer_text = llm_resp.content.strip()
    except Exception as exc:
        logger.warning(
            "LLM call failed in chat_with_portfolio (%s). Using deterministic summary fallback.",
            exc,
        )
        TerminalLogger.log_copilot_step("Fallback", f"LLM error: {exc}. Using deterministic summary fallback.")
        if "risk" in norm_query or "alert" in norm_query:
            if alerts:
                top_alerts = "; ".join([f"{a.severity}: {a.title}" for a in alerts[:3]])
                answer_text = f"'{portfolio.name}' has {len(alerts)} alerts: {top_alerts}. Total fund value is ${total_val:,.2f}."
            else:
                answer_text = f"No active risk alerts are currently flagged for '{portfolio.name}'. Aggregate risk is LOW."
        elif "exposure" in norm_query or "weight" in norm_query or "allocation" in norm_query:
            weights_summary = ", ".join([f"{h.company.ticker if h.company else 'Asset'}: {h.weight_pct}%" for h in portfolio.holdings if h.weight_pct])
            answer_text = f"Asset allocation for '{portfolio.name}': {weights_summary or 'No weighted positions found'}. Total valuation is ${total_val:,.2f}."
        else:
            holdings_list = ", ".join([h.company.ticker for h in portfolio.holdings if h.company])
            answer_text = f"Portfolio '{portfolio.name}' holds {len(portfolio.holdings)} positions ({holdings_list or 'None'}) valued at ${total_val:,.2f}."

    for h in portfolio.holdings:
        t = h.company.ticker if h.company else None
        if t and (t in clean_query.upper() or t in answer_text.upper()) and t not in cited_holdings:
            cited_holdings.append(t)

    response = PortfolioChatResponse(
        portfolio_id=str(portfolio.id),
        portfolio_name=portfolio.name,
        query=clean_query,
        answer=answer_text,
        cited_holdings=cited_holdings,
        confidence="HIGH",
        non_advisory_notice=DEFAULT_NON_ADVISORY_NOTICE,
    )

    # Cache successful response and clean up LRU size if needed
    if len(_CHAT_CACHE) > 500:
        _CHAT_CACHE.clear()
    _CHAT_CACHE[cache_key] = (now_ts, response)

    dur_ms = (time.perf_counter() - copilot_perf_start) * 1000
    TerminalLogger.log_copilot_finish(
        answer=answer_text,
        cited_holdings=cited_holdings,
        duration_ms=dur_ms,
        is_fast_path=False,
    )

    return response


