"""Tests for the data source abstraction layer."""

from datetime import date, datetime

import pandas as pd
import pytest

from trading_cli.core.data_source import (
    DataFetchRequest,
    DataFetchResult,
    DataFrequency,
    DataProvider,
    DataProviderRegistry,
    Market,
)


class MockProvider:
    """A mock data provider for testing."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.CN, Market.US]

    def fetch_stock_daily(self, request: DataFetchRequest) -> DataFetchResult:
        df = pd.DataFrame({
            "trade_date": pd.date_range("2025-01-01", periods=5),
            "open": [10.0, 10.5, 11.0, 10.8, 11.2],
            "high": [10.5, 11.0, 11.5, 11.0, 11.5],
            "low": [9.8, 10.2, 10.8, 10.5, 11.0],
            "close": [10.3, 10.8, 11.2, 10.9, 11.4],
            "vol": [1000, 1200, 1500, 1100, 1300],
        })
        return DataFetchResult(
            symbol=request.symbol,
            provider=self.name,
            market=Market.CN,
            frequency=DataFrequency.DAILY,
            row_count=len(df),
            columns=list(df.columns),
            data=df,
        )

    def check_connection(self) -> bool:
        return True


def test_mock_provider_implements_protocol():
    """MockProvider should satisfy the DataProvider protocol."""
    provider = MockProvider()
    assert isinstance(provider, DataProvider)


def test_registry_register_and_get():
    """Registry should register and retrieve providers."""
    reg = DataProviderRegistry()
    provider = MockProvider()
    reg.register(provider)
    assert reg.get("mock") is provider
    assert "mock" in reg.list_providers()


def test_registry_unknown_provider():
    """Registry should raise ValueError for unknown providers."""
    reg = DataProviderRegistry()
    with pytest.raises(ValueError, match="Unknown data provider"):
        reg.get("nonexistent")


def test_fetch_request_defaults():
    """DataFetchRequest should have sensible defaults."""
    req = DataFetchRequest(symbol="000001.SZ")
    assert req.frequency == DataFrequency.DAILY
    assert req.start_date is None
    assert req.adjust == "qfq"


def test_fetch_result_is_empty():
    """DataFetchResult.is_empty should reflect row count."""
    empty = DataFetchResult(
        symbol="TEST",
        provider="mock",
        market=Market.CN,
        frequency=DataFrequency.DAILY,
        row_count=0,
        columns=[],
        data=pd.DataFrame(),
    )
    assert empty.is_empty

    non_empty = DataFetchResult(
        symbol="TEST",
        provider="mock",
        market=Market.CN,
        frequency=DataFrequency.DAILY,
        row_count=5,
        columns=["close"],
        data=pd.DataFrame({"close": [1, 2, 3, 4, 5]}),
    )
    assert not non_empty.is_empty


def test_mock_provider_fetch():
    """Mock provider should return valid data."""
    provider = MockProvider()
    req = DataFetchRequest(symbol="000001.SZ")
    result = provider.fetch_stock_daily(req)
    assert result.row_count == 5
    assert result.symbol == "000001.SZ"
    assert "close" in result.columns
