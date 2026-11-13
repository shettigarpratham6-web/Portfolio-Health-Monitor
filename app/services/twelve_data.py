"""
Portfolio Health Monitor
Twelve Data Market Data Service
Provides real-time stock prices, batch quote retrieval, currency conversion (USD/INR),
in-memory caching with TTL, and graceful handling of unsupported exchanges and rate limits.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import get_settings

logger = logging.getLogger("agentx.services.twelve_data")


@dataclass
class QuoteResult:
    """Represents a validated stock quote result."""
    symbol: str
    price: Optional[Decimal]
    currency: str = "USD"
    exchange: Optional[str] = None
    datetime_str: Optional[str] = None
    timestamp: Optional[int] = None
    is_stale: bool = False
    source: str = "twelve_data"  # "twelve_data", "cache", "fallback_database", "unsupported"
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": float(self.price) if self.price is not None else None,
            "currency": self.currency,
            "exchange": self.exchange,
            "datetime": self.datetime_str,
            "timestamp": self.timestamp,
            "is_stale": self.is_stale,
            "source": self.source,
            "error_message": self.error_message,
        }


def is_indian_symbol(symbol: str) -> bool:
    """Helper to detect Indian equities traded in INR on NSE/BSE."""
    s = symbol.strip().upper()
    return s in (
        "PAGEIND", "RELIANCE", "TCS", "INFY", "HDFCBANK",
        "ICICIBANK", "TATAMOTORS", "ITC", "BHARTIARTL", "SBIN",
    )


class TwelveDataService:
    """
    Twelve Data API client featuring:
    - In-memory async thread-safe quote and FX rate caching.
    - Multi-symbol batch quote queries to conserve API rate limits (Free tier: 8 credits/min).
    - Foreign exchange (FX) conversion (e.g. USD/INR).
    - Non-crashing graceful fallbacks for unsupported exchanges/plans (e.g., PAGEIND on NSE).
    - Preserves recorded database values when API limits or plan restrictions occur, without fabricating data.
    """

    def __init__(self):
        self._settings = get_settings()
        self._base_url = self._settings.TWELVE_DATA_BASE_URL.rstrip("/")
        self._api_key = (
            self._settings.TWELVE_DATA_API_KEY.get_secret_value()
            if self._settings.TWELVE_DATA_API_KEY
            else None
        )
        self._cache_ttl = self._settings.TWELVE_DATA_CACHE_TTL_SECONDS
        # quote_cache: symbol -> (cached_at_datetime, QuoteResult)
        self._quote_cache: Dict[str, Tuple[datetime, QuoteResult]] = {}
        # fx_cache: pair -> (cached_at_datetime, Decimal)
        self._fx_cache: Dict[str, Tuple[datetime, Decimal]] = {}
        self._lock = asyncio.Lock()

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and len(self._api_key) > 5)

    def _get_cached_quote(self, symbol: str) -> Optional[QuoteResult]:
        """Returns cached quote if present and within TTL, else None."""
        entry = self._quote_cache.get(symbol.upper())
        if not entry:
            return None
        cached_at, quote = entry
        now = datetime.now(timezone.utc)
        if (now - cached_at).total_seconds() < self._cache_ttl:
            return quote
        return None

    def _get_stale_cached_quote(self, symbol: str) -> Optional[QuoteResult]:
        """Returns cached quote even if expired, marked as stale."""
        entry = self._quote_cache.get(symbol.upper())
        if not entry:
            return None
        _, quote = entry
        stale_quote = QuoteResult(
            symbol=quote.symbol,
            price=quote.price,
            currency=quote.currency,
            exchange=quote.exchange,
            datetime_str=quote.datetime_str,
            timestamp=quote.timestamp,
            is_stale=True,
            source="cache_stale",
            error_message="Served from stale cache due to API unavailability or rate limit",
        )
        return stale_quote

    async def get_quotes(
        self,
        symbols: List[str],
        fallback_prices: Optional[Dict[str, Decimal]] = None,
    ) -> Dict[str, QuoteResult]:
        """
        Retrieves current stock quotes for a list of symbols.
        Checks cache first, then batches remaining symbols into a single Twelve Data API call.
        Gracefully handles unsupported exchanges (e.g. PAGEIND) and rate limits.
        """
        fallback_prices = fallback_prices or {}
        cleaned_symbols = [s.strip().upper() for s in symbols if s and s.strip()]
        if not cleaned_symbols:
            return {}

        results: Dict[str, QuoteResult] = {}
        symbols_to_fetch: List[str] = []

        # 1. Check in-memory cache
        async with self._lock:
            for sym in cleaned_symbols:
                cached = self._get_cached_quote(sym)
                if cached is not None:
                    results[sym] = cached
                else:
                    symbols_to_fetch.append(sym)

        if not symbols_to_fetch:
            return results

        # 2. If API is not configured, fall back to DB prices
        if not self.is_configured:
            logger.warning("Twelve Data API key is not configured. Falling back to recorded prices.")
            for sym in symbols_to_fetch:
                fb_price = fallback_prices.get(sym)
                results[sym] = QuoteResult(
                    symbol=sym,
                    price=fb_price,
                    currency="INR" if is_indian_symbol(sym) else "USD",
                    is_stale=True,
                    source="fallback_database",
                    error_message="Twelve Data API key is not configured; using recorded database price",
                )
            return results

        # 3. Batch fetch uncached symbols
        batch_param = ",".join(symbols_to_fetch)
        endpoint = f"{self._base_url}/quote"
        params = {
            "symbol": batch_param,
            "apikey": self._api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(endpoint, params=params)

            if response.status_code == 200:
                data = response.json()
                now = datetime.now(timezone.utc)

                # If single symbol queried, Twelve Data returns a single dict rather than nested by symbol
                if len(symbols_to_fetch) == 1 and "symbol" in data:
                    data = {symbols_to_fetch[0]: data}

                async with self._lock:
                    for sym in symbols_to_fetch:
                        item = data.get(sym) if isinstance(data, dict) else None

                        # Handle successful quote
                        if item and isinstance(item, dict) and "close" in item and item.get("status") != "error":
                            try:
                                close_dec = Decimal(str(item["close"]))
                                quote = QuoteResult(
                                    symbol=sym,
                                    price=close_dec,
                                    currency=item.get("currency", "USD"),
                                    exchange=item.get("exchange"),
                                    datetime_str=item.get("datetime"),
                                    timestamp=item.get("timestamp"),
                                    is_stale=False,
                                    source="twelve_data",
                                )
                                self._quote_cache[sym] = (now, quote)
                                results[sym] = quote
                                continue
                            except (InvalidOperation, TypeError) as conv_err:
                                logger.error("Failed to parse quote close price for %s: %s", sym, conv_err)

                        # Handle unsupported symbol or plan limitation (e.g. PAGEIND 403 / 404)
                        error_msg = None
                        if item and isinstance(item, dict) and item.get("status") == "error":
                            error_msg = item.get("message", "API returned error")
                            logger.info(
                                "Twelve Data reported error for symbol %s: %s (code %s)",
                                sym,
                                error_msg,
                                item.get("code"),
                            )

                        # Fallback to database recorded price without fabricating data
                        fb_price = fallback_prices.get(sym)
                        fallback_curr = "INR" if is_indian_symbol(sym) else "USD"
                        fallback_quote = QuoteResult(
                            symbol=sym,
                            price=fb_price,
                            currency=fallback_curr,
                            is_stale=True,
                            source="fallback_database" if fb_price is not None else "unsupported",
                            error_message=(
                                f"Twelve Data plan restriction ({error_msg}); using recorded database price"
                                if fb_price is not None
                                else error_msg or "Symbol not supported by current Twelve Data plan"
                            ),
                        )
                        # Cache the fallback result so we don't re-hit 403 continuously on rapid reloads
                        self._quote_cache[sym] = (now, fallback_quote)
                        results[sym] = fallback_quote

            elif response.status_code == 429:
                logger.warning("Twelve Data API rate limit hit (HTTP 429). Serving cached or recorded prices.")
                for sym in symbols_to_fetch:
                    stale = self._get_stale_cached_quote(sym)
                    if stale:
                        results[sym] = stale
                    else:
                        fb_price = fallback_prices.get(sym)
                        results[sym] = QuoteResult(
                            symbol=sym,
                            price=fb_price,
                            currency="INR" if is_indian_symbol(sym) else "USD",
                            is_stale=True,
                            source="fallback_database",
                            error_message="Rate limit reached; served from recorded database price",
                        )
            else:
                logger.warning(
                    "Twelve Data quote request failed | status=%s | body=%s",
                    response.status_code,
                    response.text[:200],
                )
                for sym in symbols_to_fetch:
                    fb_price = fallback_prices.get(sym)
                    results[sym] = QuoteResult(
                        symbol=sym,
                        price=fb_price,
                        currency="INR" if is_indian_symbol(sym) else "USD",
                        is_stale=True,
                        source="fallback_database",
                        error_message=f"HTTP {response.status_code} error from Twelve Data",
                    )

        except Exception as exc:
            logger.error("Twelve Data fetch error for symbols %s: %s", symbols_to_fetch, exc)
            for sym in symbols_to_fetch:
                stale = self._get_stale_cached_quote(sym)
                if stale:
                    results[sym] = stale
                else:
                    fb_price = fallback_prices.get(sym)
                    results[sym] = QuoteResult(
                        symbol=sym,
                        price=fb_price,
                        currency="INR" if is_indian_symbol(sym) else "USD",
                        is_stale=True,
                        source="fallback_database",
                        error_message=f"Network exception: {str(exc)}",
                    )

        return results

    async def get_exchange_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """
        Retrieves real-time foreign exchange rate from Twelve Data.
        Example: USD/INR.
        Uses in-memory caching with TTL to avoid consuming free rate limit credits.
        """
        from_curr = from_currency.strip().upper()
        to_curr = to_currency.strip().upper()

        if from_curr == to_curr:
            return Decimal("1.0")

        pair = f"{from_curr}/{to_curr}"
        inverse_pair = f"{to_curr}/{from_curr}"
        now = datetime.now(timezone.utc)

        # Check FX cache
        async with self._lock:
            if pair in self._fx_cache:
                cached_at, rate = self._fx_cache[pair]
                if (now - cached_at).total_seconds() < self._cache_ttl:
                    return rate
            if inverse_pair in self._fx_cache:
                cached_at, inv_rate = self._fx_cache[inverse_pair]
                if (now - cached_at).total_seconds() < self._cache_ttl and inv_rate > 0:
                    return (Decimal("1.0") / inv_rate)

        # Default fallback if unconfigured
        if not self.is_configured:
            # Conservative baseline exchange rate if unconfigured
            if pair == "USD/INR":
                return Decimal("86.50")
            elif pair == "INR/USD":
                return Decimal("1.0") / Decimal("86.50")
            return Decimal("1.0")

        # Fetch live FX rate
        try:
            endpoint = f"{self._base_url}/exchange_rate"
            params = {
                "symbol": pair,
                "apikey": self._api_key,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(endpoint, params=params)

            if resp.status_code == 200:
                data = resp.json()
                if "rate" in data:
                    rate_dec = Decimal(str(data["rate"]))
                    async with self._lock:
                        self._fx_cache[pair] = (now, rate_dec)
                    return rate_dec

            # Try inverted pair if direct pair failed
            inv_params = {
                "symbol": inverse_pair,
                "apikey": self._api_key,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                inv_resp = await client.get(endpoint, params=inv_params)

            if inv_resp.status_code == 200:
                inv_data = inv_resp.json()
                if "rate" in inv_data:
                    inv_dec = Decimal(str(inv_data["rate"]))
                    if inv_dec > 0:
                        direct_dec = Decimal("1.0") / inv_dec
                        async with self._lock:
                            self._fx_cache[inverse_pair] = (now, inv_dec)
                            self._fx_cache[pair] = (now, direct_dec)
                        return direct_dec

        except Exception as exc:
            logger.error("Failed to retrieve exchange rate for %s: %s", pair, exc)

        # Fallback to cached rate even if expired
        if pair in self._fx_cache:
            return self._fx_cache[pair][1]

        # Standard known approximate baseline for USD/INR if API unreachable
        if pair == "USD/INR":
            return Decimal("86.50")
        elif pair == "INR/USD":
            return Decimal("1.0") / Decimal("86.50")

        return Decimal("1.0")

    async def convert_currency(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> Decimal:
        """Converts an amount from one currency to another using the latest FX rate."""
        if from_currency.strip().upper() == to_currency.strip().upper():
            return amount
        rate = await self.get_exchange_rate(from_currency, to_currency)
        return amount * rate


# Singleton instance
_twelve_data_service: Optional[TwelveDataService] = None


def get_twelve_data_service() -> TwelveDataService:
    global _twelve_data_service
    if _twelve_data_service is None:
        _twelve_data_service = TwelveDataService()
    return _twelve_data_service

