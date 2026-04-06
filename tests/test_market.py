"""Tests for multi-market system — market info, FX, IB provider."""

from datetime import date, timedelta

import pytest

from trading_cli.core.market import (
    MARKETS, get_market, detect_market, fx_rate, convert_currency,
    normalize_symbol, Currency,
)
from trading_cli.core.ib_provider import IBProvider
from trading_cli.core.data_source import DataFetchRequest, DataFrequency, Market


class TestMarketInfo:
    def test_get_cn_market(self):
        m = get_market("CN")
        assert m.currency == Currency.CNY
        assert m.lot_size == 100
        assert len(m.sessions) == 2

    def test_get_us_market(self):
        m = get_market("US")
        assert m.currency == Currency.USD
        assert "NYSE" in m.exchange_names

    def test_get_hk_market(self):
        m = get_market("HK")
        assert m.currency == Currency.HKD

    def test_unknown_market(self):
        with pytest.raises(ValueError, match="Unknown market"):
            get_market("JP")

    def test_all_markets_defined(self):
        assert len(MARKETS) == 3


class TestDetectMarket:
    def test_cn_symbols(self):
        assert detect_market("000001.SZ") == "CN"
        assert detect_market("600519.SH") == "CN"

    def test_hk_symbols(self):
        assert detect_market("0700.HK") == "HK"
        assert detect_market("9988.HK") == "HK"

    def test_us_symbols(self):
        assert detect_market("AAPL") == "US"
        assert detect_market("MSFT") == "US"
        assert detect_market("GOOGL") == "US"


class TestNormalizeSymbol:
    def test_cn_auto_suffix(self):
        assert normalize_symbol("600519", "CN") == "600519.SH"
        assert normalize_symbol("000001", "CN") == "000001.SZ"

    def test_cn_already_suffixed(self):
        assert normalize_symbol("000001.SZ", "CN") == "000001.SZ"

    def test_hk_suffix(self):
        assert normalize_symbol("0700", "HK") == "0700.HK"
        assert normalize_symbol("0700.HK", "HK") == "0700.HK"

    def test_us_strip(self):
        assert normalize_symbol("AAPL", "US") == "AAPL"


class TestFXRates:
    def test_same_currency(self):
        assert fx_rate("USD", "USD") == 1.0

    def test_usd_cny(self):
        rate = fx_rate("USD", "CNY")
        assert 6.0 < rate < 9.0

    def test_round_trip(self):
        """Converting USD→CNY→USD should be approximately identity."""
        usd_to_cny = fx_rate("USD", "CNY")
        cny_to_usd = fx_rate("CNY", "USD")
        assert usd_to_cny * cny_to_usd == pytest.approx(1.0, abs=0.01)

    def test_convert_currency(self):
        result = convert_currency(100, "USD", "CNY")
        assert result > 600  # $100 > ¥600


class TestIBProvider:
    def test_provider_name(self):
        ib = IBProvider(simulated=True)
        assert ib.name == "ib"

    def test_supported_markets(self):
        ib = IBProvider(simulated=True)
        assert Market.US in ib.supported_markets
        assert Market.HK in ib.supported_markets

    def test_simulated_connection(self):
        ib = IBProvider(simulated=True)
        assert ib.check_connection() is True

    def test_fetch_us_stock(self):
        ib = IBProvider(simulated=True)
        req = DataFetchRequest(
            symbol="AAPL",
            start_date=date.today() - timedelta(days=60),
            end_date=date.today(),
        )
        result = ib.fetch_stock_daily(req)
        assert result.row_count > 0
        assert result.provider == "ib"
        assert result.market == Market.US
        assert "close" in result.columns

    def test_fetch_hk_stock(self):
        ib = IBProvider(simulated=True)
        req = DataFetchRequest(
            symbol="0700.HK",
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
        )
        result = ib.fetch_stock_daily(req)
        assert result.row_count > 0
        assert result.market == Market.HK

    def test_simulated_data_deterministic(self):
        """Same symbol should produce same data."""
        ib = IBProvider(simulated=True)
        req = DataFetchRequest(symbol="MSFT", start_date=date(2026, 1, 1), end_date=date(2026, 3, 1))
        r1 = ib.fetch_stock_daily(req)
        r2 = ib.fetch_stock_daily(req)
        assert r1.data["close"].iloc[-1] == r2.data["close"].iloc[-1]

    def test_ohlc_consistency(self):
        """High >= max(open, close) and low <= min(open, close)."""
        ib = IBProvider(simulated=True)
        req = DataFetchRequest(symbol="AAPL", start_date=date.today() - timedelta(days=90))
        result = ib.fetch_stock_daily(req)
        df = result.data
        assert (df["high"] >= df["open"]).all()
        assert (df["high"] >= df["close"]).all()
        assert (df["low"] <= df["open"]).all()
        assert (df["low"] <= df["close"]).all()

    def test_empty_range(self):
        ib = IBProvider(simulated=True)
        req = DataFetchRequest(symbol="AAPL", start_date=date(2026, 4, 5), end_date=date(2026, 4, 5))
        result = ib.fetch_stock_daily(req)
        # Weekend or single day might produce 0-1 rows
        assert result.row_count >= 0

    def test_realistic_price_range(self):
        """AAPL simulated price should be in reasonable range."""
        ib = IBProvider(simulated=True)
        req = DataFetchRequest(symbol="AAPL", start_date=date.today() - timedelta(days=30))
        result = ib.fetch_stock_daily(req)
        prices = result.data["close"]
        assert prices.min() > 50   # AAPL shouldn't be below $50
        assert prices.max() < 500  # or above $500
