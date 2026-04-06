"""Multi-market management — market metadata, trading hours, and FX rates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timezone, timedelta
from enum import Enum
from typing import Optional


class Currency(str, Enum):
    CNY = "CNY"
    HKD = "HKD"
    USD = "USD"


@dataclass(frozen=True)
class TradingSession:
    """A single trading session within a market day."""

    open: time
    close: time
    label: str = ""


@dataclass(frozen=True)
class MarketInfo:
    """Static metadata about a market."""

    code: str  # CN, HK, US
    name: str
    currency: Currency
    timezone_offset: float  # hours from UTC
    sessions: tuple[TradingSession, ...]
    lot_size: int  # minimum trade unit
    tick_size: float  # minimum price movement
    exchange_names: tuple[str, ...]  # e.g. ("SSE", "SZSE")

    @property
    def timezone_name(self) -> str:
        h = int(self.timezone_offset)
        return f"UTC{'+' if h >= 0 else ''}{h}"


# ---------------------------------------------------------------------------
# Market definitions
# ---------------------------------------------------------------------------

MARKETS: dict[str, MarketInfo] = {
    "CN": MarketInfo(
        code="CN",
        name="China A-Shares",
        currency=Currency.CNY,
        timezone_offset=8,
        sessions=(
            TradingSession(time(9, 30), time(11, 30), "Morning"),
            TradingSession(time(13, 0), time(15, 0), "Afternoon"),
        ),
        lot_size=100,
        tick_size=0.01,
        exchange_names=("SSE", "SZSE"),
    ),
    "HK": MarketInfo(
        code="HK",
        name="Hong Kong",
        currency=Currency.HKD,
        timezone_offset=8,
        sessions=(
            TradingSession(time(9, 30), time(12, 0), "Morning"),
            TradingSession(time(13, 0), time(16, 0), "Afternoon"),
        ),
        lot_size=1,
        tick_size=0.01,
        exchange_names=("HKEX",),
    ),
    "US": MarketInfo(
        code="US",
        name="United States",
        currency=Currency.USD,
        timezone_offset=-4,  # EDT
        sessions=(TradingSession(time(9, 30), time(16, 0), "Regular"),),
        lot_size=1,
        tick_size=0.01,
        exchange_names=("NYSE", "NASDAQ", "AMEX"),
    ),
}


def get_market(code: str) -> MarketInfo:
    """Get market info by code."""
    code = code.upper()
    if code not in MARKETS:
        raise ValueError(f"Unknown market: {code}. Available: {', '.join(MARKETS)}")
    return MARKETS[code]


def detect_market(symbol: str) -> str:
    """Detect market from symbol format."""
    symbol = symbol.upper()
    # A-shares: 6-digit + .SH/.SZ
    if symbol.endswith(".SH") or symbol.endswith(".SZ"):
        return "CN"
    # HK: 4-5 digit + .HK
    if symbol.endswith(".HK"):
        return "HK"
    # US: pure alpha or with common suffixes
    if symbol.isalpha() or "." not in symbol:
        return "US"
    # Fallback
    return "US"


# ---------------------------------------------------------------------------
# Simple FX rates (static / demo — real rates from API in production)
# ---------------------------------------------------------------------------

_FX_RATES: dict[tuple[str, str], float] = {
    ("USD", "CNY"): 7.25,
    ("USD", "HKD"): 7.80,
    ("HKD", "CNY"): 0.93,
    ("CNY", "USD"): 1 / 7.25,
    ("HKD", "USD"): 1 / 7.80,
    ("CNY", "HKD"): 1 / 0.93,
}


def fx_rate(from_ccy: str, to_ccy: str) -> float:
    """Get FX rate for currency conversion."""
    from_ccy, to_ccy = from_ccy.upper(), to_ccy.upper()
    if from_ccy == to_ccy:
        return 1.0
    return _FX_RATES.get((from_ccy, to_ccy), 1.0)


def convert_currency(amount: float, from_ccy: str, to_ccy: str) -> float:
    """Convert amount between currencies."""
    return amount * fx_rate(from_ccy, to_ccy)


# ---------------------------------------------------------------------------
# Symbol normalization
# ---------------------------------------------------------------------------


def normalize_symbol(symbol: str, market: str) -> str:
    """Normalize a symbol to its canonical form for a given market."""
    symbol = symbol.upper().strip()
    market = market.upper()

    if market == "CN":
        if "." not in symbol:
            if symbol.startswith("6"):
                return f"{symbol}.SH"
            return f"{symbol}.SZ"
        return symbol

    if market == "HK":
        base = symbol.replace(".HK", "")
        return f"{base}.HK"

    # US: strip any suffix
    if market == "US":
        return symbol.split(".")[0]

    return symbol
