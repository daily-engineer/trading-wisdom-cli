"""Data source abstraction layer."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional, Protocol, runtime_checkable

import pandas as pd
from pydantic import BaseModel, Field


class Market(str, Enum):
    """Supported markets."""

    CN = "CN"  # A-shares
    HK = "HK"  # Hong Kong
    US = "US"  # United States


class DataFrequency(str, Enum):
    """Data frequency."""

    DAILY = "D"
    WEEKLY = "W"
    MONTHLY = "M"
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    MIN_60 = "60min"


class DataFetchRequest(BaseModel):
    """Request parameters for fetching market data."""

    symbol: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    frequency: DataFrequency = DataFrequency.DAILY
    market: Optional[Market] = None
    adjust: str = "qfq"  # qfq=前复权, hfq=后复权, None=不复权


class DataFetchResult(BaseModel):
    """Result of a data fetch operation."""

    model_config = {"arbitrary_types_allowed": True}

    symbol: str
    provider: str
    market: Market
    frequency: DataFrequency
    row_count: int
    columns: list[str]
    data: pd.DataFrame
    fetched_at: datetime = Field(default_factory=datetime.now)

    @property
    def is_empty(self) -> bool:
        return self.row_count == 0


@runtime_checkable
class DataProvider(Protocol):
    """Protocol for data providers."""

    @property
    def name(self) -> str:
        """Provider name."""
        ...

    @property
    def supported_markets(self) -> list[Market]:
        """Markets supported by this provider."""
        ...

    def fetch_stock_daily(self, request: DataFetchRequest) -> DataFetchResult:
        """Fetch daily stock data."""
        ...

    def check_connection(self) -> bool:
        """Check if the provider is accessible."""
        ...


class DataProviderRegistry:
    """Registry for data providers."""

    def __init__(self) -> None:
        self._providers: dict[str, DataProvider] = {}

    def register(self, provider: DataProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> DataProvider:
        if name not in self._providers:
            available = ", ".join(self._providers.keys()) or "none"
            raise ValueError(f"Unknown data provider: '{name}'. Available: {available}")
        return self._providers[name]

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())


# Global registry
registry = DataProviderRegistry()
