"""Tests for capital flow engine and CLI commands."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from click.testing import CliRunner

from trading_cli.core.capital_flow import (
    calculate_net_inflow,
    calculate_flow_intensity,
    detect_signal,
    calculate_streak,
)
from trading_cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_df(
    buy_lg: list[float],
    sell_lg: list[float],
    buy_elg: list[float],
    sell_elg: list[float],
    close: list[float],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "buy_lg_vol": buy_lg,
            "sell_lg_vol": sell_lg,
            "buy_elg_vol": buy_elg,
            "sell_elg_vol": sell_elg,
            "close": close,
        }
    )


def _make_flow_df(days: int = 10) -> pd.DataFrame:
    """Return a realistic-looking moneyflow DataFrame."""
    import numpy as np

    rng = range(days)
    dates = pd.date_range("2026-01-01", periods=days)
    closes = [10.0 + i * 0.1 for i in rng]
    buy_lg = [100.0 + i * 5 for i in rng]
    sell_lg = [80.0 + i * 3 for i in rng]
    buy_elg = [50.0 + i * 2 for i in rng]
    sell_elg = [40.0 + i * 1 for i in rng]
    net_mf_vol = [b - s for b, s in zip(buy_lg, sell_lg)]
    return pd.DataFrame(
        {
            "trade_date": dates,
            "close": closes,
            "buy_sm_vol": [20.0] * days,
            "sell_sm_vol": [18.0] * days,
            "buy_md_vol": [60.0] * days,
            "sell_md_vol": [55.0] * days,
            "buy_lg_vol": buy_lg,
            "sell_lg_vol": sell_lg,
            "buy_elg_vol": buy_elg,
            "sell_elg_vol": sell_elg,
            "net_mf_vol": net_mf_vol,
        }
    )


# ---------------------------------------------------------------------------
# Core engine tests
# ---------------------------------------------------------------------------


class TestCalculateNetInflow:
    def test_positive_inflow(self):
        df = _make_df(
            buy_lg=[200], sell_lg=[100], buy_elg=[50], sell_elg=[30], close=[10.0]
        )
        result = calculate_net_inflow(df)
        # net_vol = 200 + 50 - 100 - 30 = 120; × 10 = 1200
        assert result.iloc[0] == pytest.approx(1200.0)

    def test_negative_inflow(self):
        df = _make_df(
            buy_lg=[50], sell_lg=[200], buy_elg=[10], sell_elg=[100], close=[5.0]
        )
        result = calculate_net_inflow(df)
        # net_vol = 50 + 10 - 200 - 100 = -240; × 5 = -1200
        assert result.iloc[0] == pytest.approx(-1200.0)

    def test_zero_inflow(self):
        df = _make_df(
            buy_lg=[100], sell_lg=[100], buy_elg=[50], sell_elg=[50], close=[15.0]
        )
        result = calculate_net_inflow(df)
        assert result.iloc[0] == pytest.approx(0.0)

    def test_multiple_rows(self):
        df = _make_df(
            buy_lg=[100, 200],
            sell_lg=[80, 250],
            buy_elg=[20, 30],
            sell_elg=[10, 20],
            close=[10.0, 12.0],
        )
        result = calculate_net_inflow(df)
        assert len(result) == 2
        # row 0: (100+20-80-10)*10 = 300; row 1: (200+30-250-20)*12 = -480
        assert result.iloc[0] == pytest.approx(300.0)
        assert result.iloc[1] == pytest.approx(-480.0)

    def test_returns_series(self):
        df = _make_df([10], [5], [2], [1], [20.0])
        result = calculate_net_inflow(df)
        assert isinstance(result, pd.Series)


class TestCalculateFlowIntensity:
    def test_basic_intensity(self):
        net = pd.Series([1000.0])
        total = pd.Series([5000.0])
        result = calculate_flow_intensity(net, total)
        assert result.iloc[0] == pytest.approx(20.0)

    def test_zero_total_vol(self):
        net = pd.Series([100.0])
        total = pd.Series([0.0])
        result = calculate_flow_intensity(net, total)
        assert result.iloc[0] == pytest.approx(0.0)

    def test_clipped_to_100(self):
        """Even with huge net inflow the result stays ≤ 100."""
        net = pd.Series([1_000_000.0])
        total = pd.Series([1.0])
        result = calculate_flow_intensity(net, total)
        assert result.iloc[0] == pytest.approx(100.0)

    def test_negative_inflow_uses_abs(self):
        """Intensity is always non-negative (uses abs)."""
        net = pd.Series([-500.0])
        total = pd.Series([1000.0])
        result = calculate_flow_intensity(net, total)
        assert result.iloc[0] >= 0

    def test_multiple_rows(self):
        net = pd.Series([200.0, -400.0])
        total = pd.Series([1000.0, 2000.0])
        result = calculate_flow_intensity(net, total)
        assert result.iloc[0] == pytest.approx(20.0)
        assert result.iloc[1] == pytest.approx(20.0)


class TestDetectSignal:
    def test_xichou(self):
        price_chg = pd.Series([-0.01])
        net_inflow = pd.Series([1000.0])
        result = detect_signal(price_chg, net_inflow)
        assert result.iloc[0] == "吸筹"

    def test_pafa(self):
        price_chg = pd.Series([0.02])
        net_inflow = pd.Series([-500.0])
        result = detect_signal(price_chg, net_inflow)
        assert result.iloc[0] == "派发"

    def test_neutral_up_with_inflow(self):
        price_chg = pd.Series([0.03])
        net_inflow = pd.Series([300.0])
        result = detect_signal(price_chg, net_inflow)
        assert result.iloc[0] == "中性"

    def test_neutral_down_with_outflow(self):
        price_chg = pd.Series([-0.02])
        net_inflow = pd.Series([-200.0])
        result = detect_signal(price_chg, net_inflow)
        assert result.iloc[0] == "中性"

    def test_neutral_zero_change(self):
        price_chg = pd.Series([0.0])
        net_inflow = pd.Series([500.0])
        result = detect_signal(price_chg, net_inflow)
        assert result.iloc[0] == "中性"

    def test_mixed_series(self):
        price_chg = pd.Series([-0.01, 0.02, 0.01])
        net_inflow = pd.Series([100.0, -200.0, 50.0])
        result = detect_signal(price_chg, net_inflow)
        assert result.tolist() == ["吸筹", "派发", "中性"]

    def test_returns_series(self):
        result = detect_signal(pd.Series([0.0]), pd.Series([0.0]))
        assert isinstance(result, pd.Series)


class TestCalculateStreak:
    def test_positive_streak(self):
        net = pd.Series([100.0, 200.0, 150.0])
        assert calculate_streak(net) == 3

    def test_negative_streak(self):
        net = pd.Series([-100.0, -200.0])
        assert calculate_streak(net) == -2

    def test_mixed_streak_last_positive(self):
        net = pd.Series([-50.0, 100.0, 200.0])
        assert calculate_streak(net) == 2

    def test_mixed_streak_last_negative(self):
        net = pd.Series([100.0, -200.0, -150.0])
        assert calculate_streak(net) == -2

    def test_zero_last_value(self):
        net = pd.Series([100.0, 200.0, 0.0])
        assert calculate_streak(net) == 0

    def test_empty_series(self):
        assert calculate_streak(pd.Series([], dtype=float)) == 0

    def test_single_positive(self):
        assert calculate_streak(pd.Series([500.0])) == 1

    def test_single_negative(self):
        assert calculate_streak(pd.Series([-500.0])) == -1


# ---------------------------------------------------------------------------
# CLI tests (with mocked _fetch_capital_flow)
# ---------------------------------------------------------------------------

runner = CliRunner()
_PATCH_TARGET = "trading_cli.commands.capital_flow_cmd._fetch_capital_flow"


class TestCapitalFlowCLI:
    def test_help(self):
        result = runner.invoke(cli, ["capital-flow", "--help"])
        assert result.exit_code == 0
        assert "capital-flow" in result.output.lower() or "Capital" in result.output

    def test_stock_help(self):
        result = runner.invoke(cli, ["capital-flow", "stock", "--help"])
        assert result.exit_code == 0
        assert "--days" in result.output

    def test_stock_with_data(self):
        mock_df = _make_flow_df(10)
        with patch(_PATCH_TARGET, return_value=mock_df):
            result = runner.invoke(cli, ["capital-flow", "stock", "000001.SZ"])
        assert result.exit_code == 0
        assert "资金流向" in result.output

    def test_stock_no_data(self):
        with patch(_PATCH_TARGET, return_value=pd.DataFrame()):
            result = runner.invoke(cli, ["capital-flow", "stock", "000001.SZ"])
        assert result.exit_code == 0
        assert "未找到" in result.output

    def test_stock_no_token(self):
        with patch(_PATCH_TARGET, return_value=None):
            result = runner.invoke(cli, ["capital-flow", "stock", "000001.SZ"])
        assert result.exit_code != 0

    def test_sector_with_data(self):
        mock_df = _make_flow_df(5)
        with patch(_PATCH_TARGET, return_value=mock_df):
            result = runner.invoke(cli, ["capital-flow", "sector", "--top", "3"])
        assert result.exit_code == 0
        assert "板块资金流向" in result.output

    def test_alerts_with_data(self):
        mock_df = _make_flow_df(10)
        with patch(_PATCH_TARGET, return_value=mock_df):
            result = runner.invoke(cli, ["capital-flow", "alerts", "--divergence"])
        assert result.exit_code == 0
        assert "资金流向背离预警" in result.output

    def test_alerts_no_signals(self):
        """When no divergence detected, prints 无背离信号."""
        # Build a neutral df: price up with inflow (no divergence)
        df = _make_flow_df(5)
        with patch(_PATCH_TARGET, return_value=df):
            result = runner.invoke(cli, ["capital-flow", "alerts"])
        assert result.exit_code == 0

    def test_streak_no_results(self):
        mock_df = _make_flow_df(3)
        with patch(_PATCH_TARGET, return_value=mock_df):
            result = runner.invoke(
                cli, ["capital-flow", "streak", "--threshold", "100"]
            )
        assert result.exit_code == 0
        assert "无连续" in result.output

    def test_streak_with_data(self):
        # Create a df where all net inflows are strongly positive
        df = _make_flow_df(10)
        # Make sell very small so streak is clearly positive
        df["sell_lg_vol"] = 1.0
        df["sell_elg_vol"] = 1.0
        with patch(_PATCH_TARGET, return_value=df):
            result = runner.invoke(cli, ["capital-flow", "streak", "--threshold", "3"])
        assert result.exit_code == 0

    def test_cli_registered(self):
        """capital-flow should appear in top-level --help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "capital-flow" in result.output
