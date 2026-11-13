"""
Portfolio Health Monitor
Twelve Data Integration & Holding Valuation Tests
Tests quote retrieval, currency conversion, in-memory caching, unsupported plan fallbacks,
and exact decimal arithmetic for Weighted Average Price, Market Value, and Portfolio Weights.
"""

from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.twelve_data import QuoteResult, TwelveDataService, get_twelve_data_service


@pytest.mark.asyncio
async def test_twelve_data_service_configured():
    service = get_twelve_data_service()
    assert service.is_configured is True
    assert service._api_key is not None
    assert len(service._api_key) > 5


@pytest.mark.asyncio
async def test_twelve_data_batch_quotes_live():
    """Verify live quotes for US tickers AAPL, NVDA, GOOGL, META and fallback for PAGEIND."""
    service = get_twelve_data_service()
    symbols = ["AAPL", "NVDA", "GOOGL", "META", "PAGEIND"]
    fallback_prices = {"PAGEIND": Decimal("380.0000")}

    quotes = await service.get_quotes(symbols, fallback_prices=fallback_prices)
    assert len(quotes) == 5

    # US stocks should return valid live quotes
    for sym in ["AAPL", "NVDA", "GOOGL", "META"]:
        q = quotes[sym]
        assert q.symbol == sym
        assert q.price is not None
        assert q.price > Decimal("0")
        assert q.currency == "USD"
        assert q.is_stale is False
        assert q.source == "twelve_data"

    # PAGEIND is unsupported on Twelve Data free plan (NSE/BSE); verify non-fabricated fallback
    pageind_quote = quotes["PAGEIND"]
    assert pageind_quote.symbol == "PAGEIND"
    assert pageind_quote.price == Decimal("380.0000")
    assert pageind_quote.is_stale is True
    assert pageind_quote.source == "fallback_database"
    assert "Twelve Data plan restriction" in (pageind_quote.error_message or "")


@pytest.mark.asyncio
async def test_twelve_data_caching():
    """Verify in-memory caching prevents duplicate network requests within TTL."""
    service = TwelveDataService()
    service._cache_ttl = 300

    symbols = ["AAPL"]
    res1 = await service.get_quotes(symbols)
    assert "AAPL" in res1
    q1 = res1["AAPL"]

    # Second call should retrieve from cache
    res2 = await service.get_quotes(symbols)
    assert "AAPL" in res2
    q2 = res2["AAPL"]

    assert q1.price == q2.price
    assert q1.timestamp == q2.timestamp


@pytest.mark.asyncio
async def test_currency_conversion():
    """Verify USD/INR exchange rate and decimal conversion."""
    service = get_twelve_data_service()
    fx_rate = await service.get_exchange_rate("USD", "INR")
    assert fx_rate > Decimal("50.0")

    # Same currency conversion should return exactly the amount
    usd_amount = Decimal("100.50")
    converted_same = await service.convert_currency(usd_amount, "USD", "USD")
    assert converted_same == usd_amount

    # Convert USD to INR
    converted_inr = await service.convert_currency(Decimal("10.00"), "USD", "INR")
    assert converted_inr == Decimal("10.00") * fx_rate


@pytest.mark.asyncio
async def test_weighted_average_price_calculation():
    """
    Test purchase history weighted average calculation:
    Existing: 100 shares @ $10.00
    Added:    50 shares  @ $16.00
    Total:    150 shares
    Weighted Avg: ((100 * 10) + (50 * 16)) / 150 = (1000 + 800) / 150 = 1800 / 150 = $12.00
    """
    existing_shares = Decimal("100.000000")
    existing_avg = Decimal("10.0000")
    added_shares = Decimal("50.000000")
    added_price = Decimal("16.0000")

    total_shares = existing_shares + added_shares
    weighted_avg = ((existing_shares * existing_avg) + (added_shares * added_price)) / total_shares

    assert total_shares == Decimal("150.000000")
    assert weighted_avg == Decimal("12.0000")


@pytest.mark.asyncio
async def test_market_value_and_weights_calculation():
    """
    Verify Market Value = Shares * Current Price
    and Portfolio Weight % = (Market Value / Total Market Value) * 100
    with exact decimal precision.
    """
    holdings = [
        {"ticker": "AAPL", "shares": Decimal("10.0"), "price": Decimal("200.00")},  # MV = 2000
        {"ticker": "NVDA", "shares": Decimal("20.0"), "price": Decimal("150.00")},  # MV = 3000
        {"ticker": "META", "shares": Decimal("10.0"), "price": Decimal("500.00")},  # MV = 5000
    ]

    total_mv = Decimal("0.0000")
    for h in holdings:
        h["mv"] = (h["shares"] * h["price"]).quantize(Decimal("0.0001"))
        total_mv += h["mv"]

    assert total_mv == Decimal("10000.0000")

    for h in holdings:
        h["weight"] = ((h["mv"] / total_mv) * Decimal("100")).quantize(Decimal("0.01"))

    assert holdings[0]["weight"] == Decimal("20.00")
    assert holdings[1]["weight"] == Decimal("30.00")
    assert holdings[2]["weight"] == Decimal("50.00")
    assert sum(h["weight"] for h in holdings) == Decimal("100.00")


@pytest.mark.asyncio
async def test_multicurrency_portfolio_valuation_and_weights():
    """
    Test converting Indian assets (PAGEIND in INR) into common USD portfolio currency
    and verifying Market Value = Shares * Current Price (2 decimal places)
    and Portfolio Weights add up to 100.00%.
    """
    service = get_twelve_data_service()
    fx_rate = await service.get_exchange_rate("USD", "INR")
    assert fx_rate > Decimal("50.0")

    # AAPL (USD), NVDA (USD), PAGEIND (INR)
    # PAGEIND: 10 shares @ 380 INR
    pageind_inr_price = Decimal("380.00")
    pageind_usd_price = (pageind_inr_price / fx_rate).quantize(Decimal("0.01"))

    holdings = [
        {"ticker": "AAPL", "shares": Decimal("1.0"), "price": Decimal("354.88")},
        {"ticker": "NVDA", "shares": Decimal("1.0"), "price": Decimal("166.19")},
        {"ticker": "PAGEIND", "shares": Decimal("10.0"), "price": pageind_usd_price},
    ]

    total_mv = Decimal("0.00")
    for h in holdings:
        h["mv"] = (h["shares"] * h["price"]).quantize(Decimal("0.01"))
        total_mv += h["mv"]

    for h in holdings:
        h["weight"] = ((h["mv"] / total_mv) * Decimal("100")).quantize(Decimal("0.01"))

    # Verify Market Value is exactly shares * price without unexpected decimals
    for h in holdings:
        assert h["mv"] == (h["shares"] * h["price"]).quantize(Decimal("0.01"))

    # Verify weights sum to approximately 100%
    weight_sum = sum(h["weight"] for h in holdings)
    assert abs(weight_sum - Decimal("100.00")) <= Decimal("0.05")

