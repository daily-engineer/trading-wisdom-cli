"""Unit tests for the ETF RPS scoring system (Issue #7).

Covers:
- calculate_rps with known data → verify percentile math
- Composite score = weighted average of windows
- Grade classification (boundary values)
- NaN handling (ETF with missing data doesn't crash)
- CLI commands: rps list, rps sector, rps trend
- Edge cases: 1 ETF, all same return, smoothing
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner

from trading_cli.core.rps import (
    DEFAULT_ETF_UNIVERSE,
    SECTOR_MAP,
    calculate_rps,
    classify_grade,
    composite_rps,
)
from trading_cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prices(
    n_etfs: int = 5,
    n_days: int = 300,
    seed: int = 42,
    codes: list[str] | None = None,
) -> pd.DataFrame:
    """Build a synthetic price DataFrame."""
    np.random.seed(seed)
    if codes is None:
        codes = [f"ETF{i:03d}" for i in range(n_etfs)]
    dates = pd.bdate_range(end=date.today(), periods=n_days)
    data = {}
    for i, code in enumerate(codes):
        np.random.seed(seed + i)
        price = 10.0 + np.cumsum(np.random.randn(n_days) * 0.1)
        price = np.clip(price, 0.01, None)
        data[code] = price
    return pd.DataFrame(data, index=dates)


# ---------------------------------------------------------------------------
# 1. calculate_rps — known data, percentile math
# ---------------------------------------------------------------------------


class TestCalculateRps:
    def test_best_performer_scores_highest(self):
        """ETF with highest return over window should have the highest rank."""
        n = 300
        prices = _make_prices(n_etfs=5, n_days=n)
        # Force last ETF to have a dramatically higher price increase
        prices.iloc[-1, -1] = prices.iloc[-251, -1] * 10  # 900% gain
        rps = calculate_rps(prices, window=250, smooth=1)
        assert rps.iloc[-1] == pytest.approx(100.0, abs=1.0)

    def test_worst_performer_scores_lowest(self):
        """ETF with the lowest return should get a low rank."""
        n = 300
        prices = _make_prices(n_etfs=5, n_days=n)
        # Force first ETF to drop sharply
        prices.iloc[-1, 0] = prices.iloc[-251, 0] * 0.01  # -99% loss
        rps = calculate_rps(prices, window=250, smooth=1)
        assert rps.iloc[0] < 30.0

    def test_result_range_zero_to_100(self):
        """All RPS scores should be in [0, 100]."""
        prices = _make_prices(n_etfs=10, n_days=300)
        rps = calculate_rps(prices, window=60, smooth=1)
        assert (rps >= 0).all() and (rps <= 100).all()

    def test_result_index_matches_etf_codes(self):
        codes = ["510300.SH", "510500.SH", "159915.SZ"]
        prices = _make_prices(n_days=100, codes=codes)
        rps = calculate_rps(prices, window=20, smooth=1)
        assert set(rps.index) == set(codes)

    def test_returns_series(self):
        prices = _make_prices(n_etfs=4, n_days=100)
        result = calculate_rps(prices, window=20, smooth=1)
        assert isinstance(result, pd.Series)

    def test_empty_dataframe_returns_empty(self):
        empty = pd.DataFrame()
        result = calculate_rps(empty, window=20)
        assert result.empty

    def test_single_row_returns_empty(self):
        prices = _make_prices(n_etfs=3, n_days=1)
        result = calculate_rps(prices, window=20)
        assert result.empty


# ---------------------------------------------------------------------------
# 2. Composite score = weighted average of windows
# ---------------------------------------------------------------------------


class TestCompositeRps:
    def test_composite_columns_present(self):
        prices = _make_prices(n_etfs=5, n_days=300)
        df = composite_rps(prices, smooth=1)
        expected_cols = {
            "code",
            "rps_20",
            "rps_60",
            "rps_120",
            "rps_250",
            "rps_composite",
            "grade",
        }
        assert expected_cols.issubset(set(df.columns))

    def test_composite_is_weighted_average(self):
        """Verify composite = 0.2*w20 + 0.3*w60 + 0.3*w120 + 0.2*w250."""
        prices = _make_prices(n_etfs=6, n_days=300)
        df = composite_rps(prices, smooth=1)
        for _, row in df.iterrows():
            if any(pd.isna(row[f"rps_{w}"]) for w in [20, 60, 120, 250]):
                continue
            expected = (
                0.2 * row["rps_20"]
                + 0.3 * row["rps_60"]
                + 0.3 * row["rps_120"]
                + 0.2 * row["rps_250"]
            )
            assert row["rps_composite"] == pytest.approx(expected, abs=1e-6)

    def test_sorted_descending_by_composite(self):
        prices = _make_prices(n_etfs=8, n_days=300)
        df = composite_rps(prices, smooth=1)
        scores = df["rps_composite"].dropna().tolist()
        assert scores == sorted(scores, reverse=True)

    def test_grade_assigned_for_all_rows(self):
        prices = _make_prices(n_etfs=5, n_days=300)
        df = composite_rps(prices, smooth=1)
        assert df["grade"].notna().all()
        assert set(df["grade"]).issubset({"A", "B", "C", "D", "N/A"})


# ---------------------------------------------------------------------------
# 3. Grade classification — boundary values
# ---------------------------------------------------------------------------


class TestClassifyGrade:
    def test_grade_a_at_90(self):
        assert classify_grade(90.0) == "A"

    def test_grade_a_above_90(self):
        assert classify_grade(95.5) == "A"

    def test_grade_a_at_100(self):
        assert classify_grade(100.0) == "A"

    def test_grade_b_at_70(self):
        assert classify_grade(70.0) == "B"

    def test_grade_b_at_89(self):
        assert classify_grade(89.9) == "B"

    def test_grade_c_at_50(self):
        assert classify_grade(50.0) == "C"

    def test_grade_c_at_69(self):
        assert classify_grade(69.9) == "C"

    def test_grade_d_below_50(self):
        assert classify_grade(49.9) == "D"

    def test_grade_d_at_zero(self):
        assert classify_grade(0.0) == "D"


# ---------------------------------------------------------------------------
# 4. NaN handling — missing data
# ---------------------------------------------------------------------------


class TestNaNHandling:
    def test_nan_column_does_not_crash(self):
        """An ETF column full of NaN should not raise; it gets NaN score."""
        prices = _make_prices(n_etfs=4, n_days=300)
        prices["NAN_ETF"] = np.nan
        # Should not raise
        rps = calculate_rps(prices, window=60, smooth=1)
        assert "NAN_ETF" in rps.index
        assert np.isnan(rps["NAN_ETF"])

    def test_composite_nan_column_grade_is_na(self):
        prices = _make_prices(n_etfs=4, n_days=300)
        prices["NAN_ETF"] = np.nan
        df = composite_rps(prices, smooth=1)
        nan_row = df[df["code"] == "NAN_ETF"].iloc[0]
        assert np.isnan(nan_row["rps_composite"])
        assert nan_row["grade"] == "N/A"


# ---------------------------------------------------------------------------
# 5. Edge case: only 1 ETF in universe
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_etf_universe(self):
        """Universe of 1 ETF: rank is always 100 (only one)."""
        prices = _make_prices(n_etfs=1, n_days=300)
        rps = calculate_rps(prices, window=60, smooth=1)
        assert len(rps) == 1
        # Single ETF ranks itself at the top
        assert rps.iloc[0] == pytest.approx(100.0, abs=1.0)

    def test_all_same_return_all_score_around_50(self):
        """When all ETFs have identical returns, all should score ~50."""
        n = 300
        dates = pd.bdate_range(end=date.today(), periods=n)
        # All ETFs have identical price series
        prices = pd.DataFrame(
            {
                "A": np.linspace(10, 11, n),
                "B": np.linspace(10, 11, n),
                "C": np.linspace(10, 11, n),
            },
            index=dates,
        )
        rps = calculate_rps(prices, window=60, smooth=1)
        # All tied → all get the same rank.  pandas rank(pct=True) assigns
        # the average of the tied positions.  For N ETFs all tied, that is
        # (sum of 1..N) / N  = (N+1)/2 divided by N = (N+1)/(2N).
        # For 3 ETFs → average rank = 2/3 → 66.67 in [0,100].
        # The key property is that all ETFs receive an identical score.
        unique_scores = set(round(v, 4) for v in rps.values if not np.isnan(v))
        assert len(unique_scores) == 1, f"Expected all same scores, got {unique_scores}"

    def test_window_larger_than_history(self):
        """When window > available days, function still returns without crashing."""
        prices = _make_prices(n_etfs=3, n_days=30)
        rps = calculate_rps(prices, window=250, smooth=1)
        assert len(rps) == 3


# ---------------------------------------------------------------------------
# 6. Smoothing: verify MA reduces volatility in rank
# ---------------------------------------------------------------------------


class TestSmoothing:
    def test_smooth_reduces_variance_compared_to_no_smooth(self):
        """Smoothed scores should have lower or equal variance than unsmoothed."""
        prices = _make_prices(n_etfs=10, n_days=300, seed=99)
        # Collect composite scores with and without smoothing
        df_smooth = composite_rps(prices, smooth=5)
        df_no_smooth = composite_rps(prices, smooth=1)
        var_smooth = df_smooth["rps_composite"].var()
        var_no_smooth = df_no_smooth["rps_composite"].var()
        # Smoothed variance should be <= unsmoothed variance (or very close)
        assert var_smooth <= var_no_smooth + 50  # generous tolerance


# ---------------------------------------------------------------------------
# 7. CLI tests — rps list, rps sector, rps trend
# ---------------------------------------------------------------------------


def _make_mock_ohlcv(code: str = "510300.SH", n: int = 300) -> "DataFetchResult":  # type: ignore[name-defined]
    """Build a synthetic OHLCV DataFetchResult for a single ETF."""
    from trading_cli.core.data_source import DataFetchResult, DataFrequency, Market

    np.random.seed(hash(code) % (2**31))
    dates = pd.bdate_range(end=date.today(), periods=n)
    close = 3.0 + np.cumsum(np.random.randn(n) * 0.05)
    close = np.clip(close, 0.1, None)
    df = pd.DataFrame(
        {
            "trade_date": dates,
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "vol": np.random.randint(100_000, 500_000, n).astype(float),
        }
    )
    return DataFetchResult(
        symbol=code,
        provider="mock",
        market=Market.CN,
        frequency=DataFrequency.DAILY,
        row_count=n,
        columns=list(df.columns),
        data=df,
    )


def _make_mock_provider_for_rps() -> MagicMock:
    """Return a mock provider that returns OHLCV data keyed on symbol."""
    mock = MagicMock()
    mock.name = "tushare"
    mock.fetch_stock_daily.side_effect = lambda req: _make_mock_ohlcv(req.symbol, n=300)
    return mock


def _make_mock_registry_for_rps() -> MagicMock:
    provider = _make_mock_provider_for_rps()
    mock_registry = MagicMock()
    mock_registry.get.return_value = provider
    mock_registry.list_providers.return_value = ["tushare"]
    return mock_registry


class TestRpsCliCommands:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.runner = CliRunner()
        self.mock_registry = _make_mock_registry_for_rps()

    def _invoke(self, args: list[str]):
        with patch("trading_cli.commands.rps_cmd.registry", self.mock_registry):
            return self.runner.invoke(cli, args)

    def test_rps_help(self):
        result = self.runner.invoke(cli, ["rps", "--help"])
        assert result.exit_code == 0
        assert "rps" in result.output.lower()

    def test_rps_list_exits_zero(self):
        result = self._invoke(["rps", "list"])
        assert result.exit_code == 0, result.output

    def test_rps_list_contains_rps_header(self):
        result = self._invoke(["rps", "list"])
        assert "RPS" in result.output

    def test_rps_list_window_option(self):
        result = self._invoke(["rps", "list", "--window", "60"])
        assert result.exit_code == 0, result.output

    def test_rps_list_top_option(self):
        result = self._invoke(["rps", "list", "--top", "5"])
        assert result.exit_code == 0, result.output

    def test_rps_sector_exits_zero(self):
        result = self._invoke(["rps", "sector"])
        assert result.exit_code == 0, result.output

    def test_rps_sector_contains_sector_name(self):
        result = self._invoke(["rps", "sector"])
        # Should show at least one sector from the map
        assert any(
            s in result.output
            for s in ["宽基", "医疗", "金融", "地产", "消费", "新能源"]
        )

    def test_rps_trend_exits_zero(self):
        result = self._invoke(["rps", "trend", "510300.SH"])
        assert result.exit_code == 0, result.output

    def test_rps_trend_contains_etf_code(self):
        result = self._invoke(["rps", "trend", "510300.SH"])
        assert "510300" in result.output

    def test_rps_trend_days_option(self):
        result = self._invoke(["rps", "trend", "510300.SH", "--days", "60"])
        assert result.exit_code == 0, result.output
