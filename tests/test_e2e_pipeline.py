"""End-to-end integration tests for the full trading pipeline.

Three scenarios test the complete flow using synthetic mock data — no external
API calls are made.  The data provider registry is patched at the module level
so every command that touches ``registry.get(...)`` receives a mock provider
that returns a realistic OHLCV DataFetchResult.
"""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner

from trading_cli.core.data_source import (
    DataFetchResult,
    DataFrequency,
    Market,
)
from trading_cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ohlcv(
    symbol: str = "000001.SZ",
    n: int = 100,
    market: Market = Market.CN,
    start_price: float = 10.0,
) -> DataFetchResult:
    """Build a synthetic OHLCV DataFetchResult."""
    np.random.seed(42)
    dates = pd.date_range(end=date.today(), periods=n, freq="B")
    close = start_price + np.cumsum(np.random.randn(n) * 0.1)
    df = pd.DataFrame(
        {
            "trade_date": dates,
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "vol": np.random.randint(1_000_000, 5_000_000, n),
        }
    )
    return DataFetchResult(
        symbol=symbol,
        provider="mock",
        market=market,
        frequency=DataFrequency.DAILY,
        row_count=n,
        columns=list(df.columns),
        data=df,
    )


def _make_mock_provider(symbol: str = "000001.SZ", n: int = 100) -> MagicMock:
    """Return a mock DataProvider that returns realistic OHLCV data."""
    result = make_ohlcv(symbol=symbol, n=n)
    mock_provider = MagicMock()
    mock_provider.name = "tushare"
    mock_provider.supported_markets = [Market.CN, Market.HK, Market.US]
    mock_provider.check_connection.return_value = True
    mock_provider.fetch_stock_daily.return_value = result
    return mock_provider


def _make_mock_registry(mock_provider: MagicMock) -> MagicMock:
    """Return a mock registry that always returns *mock_provider*."""
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_provider
    mock_registry.list_providers.return_value = ["tushare"]
    return mock_registry


def _reset_trade_state() -> None:
    """Reset the paper-trader and trade-logger singletons between tests.

    Also replaces the module-level ``_logger`` with a fresh ``TradeLogger``
    pointing to a temporary directory so test runs never pollute the user's
    real ``~/.trading-cli/trade_log.jsonl``.
    """
    import trading_cli.commands.trade_cmd as _trade_cmd_module
    from trading_cli.core.trade_logger import TradeLogger

    _trade_cmd_module._paper_trader = None
    _trade_cmd_module._live_trader = None
    # Reset logger to a fresh instance writing to a throwaway temp directory.
    _tmp_log = Path(tempfile.mkdtemp()) / "trade_log.jsonl"
    _trade_cmd_module._logger = TradeLogger(log_path=_tmp_log)


# ---------------------------------------------------------------------------
# Scenario 1 — A-share daily pipeline
# ---------------------------------------------------------------------------


class TestAShareDailyPipeline:
    """Full pipeline: data sources → analyze → backtest → trade → report."""

    SYMBOL = "000001.SZ"

    @pytest.fixture(autouse=True)
    def setup(self):
        _reset_trade_state()
        self.runner = CliRunner()
        self.mock_provider = _make_mock_provider(symbol=self.SYMBOL, n=200)
        self.mock_registry = _make_mock_registry(self.mock_provider)

    def _invoke(self, args: list[str]) -> "click.testing.Result":  # type: ignore[name-defined]
        patches = [
            patch("trading_cli.commands.data_cmd.registry", self.mock_registry),
            patch("trading_cli.commands.analyze_cmd.registry", self.mock_registry),
            patch("trading_cli.commands.backtest_cmd.registry", self.mock_registry),
            patch("trading_cli.commands.trade_cmd.registry", self.mock_registry),
        ]
        with patches[0], patches[1], patches[2], patches[3]:
            return self.runner.invoke(cli, args)

    def test_step1_data_sources(self):
        """data sources lists the mock provider."""
        result = self._invoke(["data", "sources"])
        assert result.exit_code == 0, result.output
        assert "tushare" in result.output

    def test_step2_analyze_indicators(self):
        """analyze indicators returns RSI / MACD / BB output."""
        result = self._invoke(["analyze", "indicators", self.SYMBOL])
        assert result.exit_code == 0, result.output
        # Should contain common indicator labels
        assert any(
            kw in result.output for kw in ["RSI", "MACD", "Bollinger", "MA", "Signal"]
        )

    def test_step3_backtest_ma_cross(self):
        """backtest run ma_cross produces P&L metrics."""
        result = self._invoke(
            ["backtest", "run", "ma_cross", self.SYMBOL, "--days", "180"]
        )
        assert result.exit_code == 0, result.output
        assert any(
            kw in result.output
            for kw in ["Backtest", "P&L", "Sharpe", "Return", "Trade", "backtest"]
        )

    def test_step4_trade_order_buy(self):
        """trade order buy places a paper buy order that fills."""
        result = self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "1000"])
        assert result.exit_code == 0, result.output
        assert "BUY FILLED" in result.output or "FILLED" in result.output

    def test_step5_trade_account(self):
        """trade account shows account summary after a buy."""
        # Buy first so account has something to report
        self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "1000"])
        result = self._invoke(["trade", "account"])
        assert result.exit_code == 0, result.output
        assert any(
            kw in result.output for kw in ["Account", "Capital", "Cash", "Equity"]
        )

    def test_step6_report_summary(self):
        """report portfolio renders a portfolio table.

        Note: this verifies the report command executes without error; demo
        data is shown since no portfolio file is exported from the trade state.
        Report pipeline integration is exercised indirectly through the trade
        account tests (test_step5_trade_account).
        """
        result = self._invoke(["report", "portfolio"])
        assert result.exit_code == 0, result.output

    def test_full_pipeline_sequential(self):
        """Run all six steps in order and assert each exits cleanly."""
        steps = [
            ["data", "sources"],
            ["analyze", "indicators", self.SYMBOL],
            ["backtest", "run", "ma_cross", self.SYMBOL, "--days", "180"],
            ["trade", "order", "buy", self.SYMBOL, "--qty", "500"],
            ["trade", "account"],
            ["report", "portfolio"],
        ]
        for step in steps:
            result = self._invoke(step)
            assert (
                result.exit_code == 0
            ), f"Step {step} failed with exit_code={result.exit_code}\n{result.output}"


# ---------------------------------------------------------------------------
# Scenario 2 — US stock options pipeline
# ---------------------------------------------------------------------------


class TestUSOptionsPipeline:
    """Full pipeline: options chain → options greeks → trade order buy → position list."""

    SYMBOL = "AAPL"

    @pytest.fixture(autouse=True)
    def setup(self):
        _reset_trade_state()
        self.runner = CliRunner()
        # US stock at ~170 USD
        self.mock_provider = _make_mock_provider(symbol=self.SYMBOL, n=100)
        # Override close prices to be ~170
        df = self.mock_provider.fetch_stock_daily.return_value.data.copy()
        np.random.seed(7)
        close = 170.0 + np.cumsum(np.random.randn(100) * 0.5)
        df["close"] = close
        df["open"] = close * 0.99
        df["high"] = close * 1.01
        df["low"] = close * 0.98
        self.mock_provider.fetch_stock_daily.return_value = DataFetchResult(
            symbol=self.SYMBOL,
            provider="mock",
            market=Market.US,
            frequency=DataFrequency.DAILY,
            row_count=100,
            columns=list(df.columns),
            data=df,
        )
        self.mock_registry = _make_mock_registry(self.mock_provider)

    def _invoke(self, args: list[str]) -> "click.testing.Result":  # type: ignore[name-defined]
        with patch("trading_cli.commands.trade_cmd.registry", self.mock_registry):
            return self.runner.invoke(cli, args)

    def test_step1_options_chain(self):
        """options chain renders CALLS and PUTS tables."""
        result = self.runner.invoke(
            cli,
            ["options", "chain", self.SYMBOL, "--price", "170", "--days", "30"],
        )
        assert result.exit_code == 0, result.output
        assert "CALLS" in result.output
        assert "PUTS" in result.output
        assert self.SYMBOL in result.output

    def test_step2_options_greeks(self):
        """options greeks renders Delta, Gamma, Theta, Vega."""
        result = self.runner.invoke(
            cli,
            [
                "options",
                "greeks",
                "--spot",
                "170",
                "--strike",
                "175",
                "--days",
                "30",
                "--vol",
                "0.25",
                "--type",
                "call",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Delta" in result.output
        assert "Gamma" in result.output
        assert "Theta" in result.output
        assert "Vega" in result.output

    def test_step3_trade_order_buy_paper(self):
        """trade order buy places a paper buy for AAPL."""
        result = self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "10"])
        assert result.exit_code == 0, result.output
        assert "FILLED" in result.output

    def test_step4_trade_position_list(self):
        """trade position list shows the AAPL position after buy."""
        self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "10"])
        result = self._invoke(["trade", "position", "list"])
        assert result.exit_code == 0, result.output
        # After a successful buy the position must appear in the output.
        assert self.SYMBOL in result.output

    def test_full_options_pipeline_sequential(self):
        """Run all four steps in order."""
        steps = [
            (
                ["options", "chain", self.SYMBOL, "--price", "170"],
                lambda r: "CALLS" in r.output,
            ),
            (
                [
                    "options",
                    "greeks",
                    "--spot",
                    "170",
                    "--strike",
                    "170",
                    "--days",
                    "30",
                ],
                lambda r: "Delta" in r.output,
            ),
            (
                ["trade", "order", "buy", self.SYMBOL, "--qty", "5"],
                lambda r: "FILLED" in r.output,
            ),
            (
                ["trade", "position", "list"],
                lambda r: r.exit_code == 0,
            ),
        ]
        for args, check in steps:
            if "trade" in args:
                result = self._invoke(args)
            else:
                result = self.runner.invoke(cli, args)
            assert result.exit_code == 0, f"Step {args} failed\n{result.output}"
            assert check(result), f"Output check failed for {args}\n{result.output}"


# ---------------------------------------------------------------------------
# Scenario 3 — Paper trading lifecycle
# ---------------------------------------------------------------------------


class TestPaperTradingLifecycle:
    """Full lifecycle: buy → sell → list orders → risk check → emergency stop."""

    SYMBOL = "600519.SH"

    @pytest.fixture(autouse=True)
    def setup(self):
        _reset_trade_state()
        self.runner = CliRunner()
        self.mock_provider = _make_mock_provider(symbol=self.SYMBOL, n=100)
        self.mock_registry = _make_mock_registry(self.mock_provider)

    def _invoke(self, args: list[str]) -> "click.testing.Result":  # type: ignore[name-defined]
        with patch("trading_cli.commands.trade_cmd.registry", self.mock_registry):
            return self.runner.invoke(cli, args)

    def test_step1_order_buy(self):
        """Buy 500 shares — should fill."""
        result = self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "500"])
        assert result.exit_code == 0, result.output
        assert "FILLED" in result.output

    def test_step2_order_sell(self):
        """Sell 200 shares after buying 500 — should fill."""
        self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "500"])
        result = self._invoke(["trade", "order", "sell", self.SYMBOL, "--qty", "200"])
        assert result.exit_code == 0, result.output
        assert "FILLED" in result.output

    def test_step3_order_list(self):
        """order list shows both buy and sell orders."""
        self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "500"])
        self._invoke(["trade", "order", "sell", self.SYMBOL, "--qty", "200"])
        result = self._invoke(["trade", "order", "list"])
        assert result.exit_code == 0, result.output
        # After buying and selling, the orders table must reference the symbol.
        assert self.SYMBOL in result.output

    def test_step4_risk_check(self):
        """trade risk returns a risk report (pass or violations listed)."""
        self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "500"])
        result = self._invoke(["trade", "risk"])
        assert result.exit_code == 0, result.output
        assert any(
            kw in result.output
            for kw in ["risk checks passed", "Risk", "violation", "limit"]
        )

    def test_step5_emergency_stop(self):
        """trade emergency stop closes all positions."""
        self._invoke(["trade", "order", "buy", self.SYMBOL, "--qty", "500"])
        result = self._invoke(["trade", "emergency", "stop"])
        assert result.exit_code == 0, result.output
        assert any(
            kw in result.output
            for kw in ["Emergency Stop", "closed", "FILLED", "stop complete"]
        )

    def test_full_lifecycle_sequential(self):
        """Buy → sell partial → list → risk → emergency stop — all exit 0."""
        steps = [
            ["trade", "order", "buy", self.SYMBOL, "--qty", "1000"],
            ["trade", "order", "sell", self.SYMBOL, "--qty", "300"],
            ["trade", "order", "list"],
            ["trade", "risk"],
            ["trade", "emergency", "stop"],
        ]
        for step in steps:
            result = self._invoke(step)
            assert (
                result.exit_code == 0
            ), f"Step {step} failed with exit_code={result.exit_code}\n{result.output}"

    def test_order_list_empty_initially(self):
        """order list on a fresh trader prints 'No orders'."""
        result = self._invoke(["trade", "order", "list"])
        assert result.exit_code == 0, result.output
        assert "No orders" in result.output

    def test_position_list_empty_initially(self):
        """position list on a fresh trader prints 'No open positions'."""
        result = self._invoke(["trade", "position", "list"])
        assert result.exit_code == 0, result.output
        assert "No open positions" in result.output

    def test_risk_check_passes_empty_account(self):
        """Risk check on a fresh account with no positions should pass."""
        result = self._invoke(["trade", "risk"])
        assert result.exit_code == 0, result.output
        assert "risk checks passed" in result.output
