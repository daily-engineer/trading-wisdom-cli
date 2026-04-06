"""Tests for the strategy optimizer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_cli.strategy.builtin import MAStrategy, RSIStrategy, BollingerStrategy, MACDStrategy
from trading_cli.strategy.optimizer import grid_search, genetic_optimize, _score_result
from trading_cli.strategy.models import StrategyResult


def _make_test_data(n: int = 200) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.RandomState(42)
    close = 10.0 + np.cumsum(rng.randn(n) * 0.2)
    close = np.maximum(close, 1.0)  # keep positive
    return pd.DataFrame({
        "trade_date": pd.date_range("2025-01-01", periods=n),
        "open": close + rng.randn(n) * 0.05,
        "high": close + abs(rng.randn(n) * 0.2),
        "low": close - abs(rng.randn(n) * 0.2),
        "close": close,
        "vol": rng.randint(100000, 1000000, n).astype(float),
        "amount": rng.randint(1000000, 10000000, n).astype(float),
    })


class TestScoreResult:
    def test_sharpe(self):
        r = StrategyResult(strategy_name="test", symbol="T", sharpe_ratio=1.5)
        assert _score_result(r, "sharpe_ratio") == 1.5

    def test_total_pnl(self):
        r = StrategyResult(strategy_name="test", symbol="T", total_pnl=5000)
        assert _score_result(r, "total_pnl") == 5000

    def test_max_drawdown_inverted(self):
        r = StrategyResult(strategy_name="test", symbol="T", max_drawdown=-8.5)
        assert _score_result(r, "max_drawdown") == -8.5  # negated absolute


class TestGridSearch:
    def test_basic_grid(self):
        df = _make_test_data()
        result = grid_search(
            MAStrategy, df, "TEST",
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
        )
        assert result.method == "grid_search"
        assert result.total_combinations == 4
        assert len(result.all_results) == 4
        assert "fast_period" in result.best_params
        assert "slow_period" in result.best_params

    def test_grid_returns_sorted(self):
        df = _make_test_data()
        result = grid_search(
            RSIStrategy, df, "TEST",
            param_grid={"period": [7, 14], "oversold": [25, 30], "overbought": [70, 75]},
        )
        scores = [r["score"] for r in result.all_results]
        assert scores == sorted(scores, reverse=True)

    def test_grid_different_metrics(self):
        df = _make_test_data()
        r1 = grid_search(MAStrategy, df, "TEST",
                         param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
                         metric="sharpe_ratio")
        r2 = grid_search(MAStrategy, df, "TEST",
                         param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
                         metric="total_pnl")
        # Both should complete; best params may differ
        assert r1.total_combinations == r2.total_combinations == 4

    def test_grid_single_combo(self):
        df = _make_test_data()
        result = grid_search(
            MAStrategy, df, "TEST",
            param_grid={"fast_period": [10], "slow_period": [30]},
        )
        assert result.total_combinations == 1
        assert result.best_params == {"fast_period": 10, "slow_period": 30}

    def test_grid_bollinger(self):
        df = _make_test_data()
        result = grid_search(
            BollingerStrategy, df, "TEST",
            param_grid={"period": [15, 20], "std_dev": [1.5, 2.0]},
        )
        assert result.total_combinations == 4
        assert "period" in result.best_params


class TestGeneticOptimize:
    def test_basic_genetic(self):
        df = _make_test_data()
        result = genetic_optimize(
            MAStrategy, df, "TEST",
            param_ranges={"fast_period": (5, 15, 1), "slow_period": (20, 40, 5)},
            population_size=6,
            generations=3,
            seed=42,
        )
        assert result.method == "genetic"
        assert "fast_period" in result.best_params
        assert "slow_period" in result.best_params
        assert result.total_combinations > 0

    def test_genetic_respects_ranges(self):
        df = _make_test_data()
        result = genetic_optimize(
            RSIStrategy, df, "TEST",
            param_ranges={"period": (5, 20, 1), "oversold": (20, 35, 5), "overbought": (65, 80, 5)},
            population_size=6,
            generations=3,
            seed=123,
        )
        assert 5 <= result.best_params["period"] <= 20
        assert 20 <= result.best_params["oversold"] <= 35
        assert 65 <= result.best_params["overbought"] <= 80

    def test_genetic_reproducible_with_seed(self):
        df = _make_test_data()
        r1 = genetic_optimize(
            MAStrategy, df, "TEST",
            param_ranges={"fast_period": (5, 15, 1), "slow_period": (20, 40, 5)},
            population_size=6, generations=3, seed=99,
        )
        r2 = genetic_optimize(
            MAStrategy, df, "TEST",
            param_ranges={"fast_period": (5, 15, 1), "slow_period": (20, 40, 5)},
            population_size=6, generations=3, seed=99,
        )
        assert r1.best_params == r2.best_params
        assert r1.best_score == r2.best_score

    def test_genetic_different_metric(self):
        df = _make_test_data()
        result = genetic_optimize(
            MAStrategy, df, "TEST",
            param_ranges={"fast_period": (5, 15, 1), "slow_period": (20, 40, 5)},
            population_size=6, generations=2, metric="total_pnl", seed=42,
        )
        assert result.method == "genetic"

    def test_genetic_macd(self):
        df = _make_test_data(300)
        result = genetic_optimize(
            MACDStrategy, df, "TEST",
            param_ranges={"fast": (8, 16, 2), "slow": (20, 32, 2), "signal": (5, 13, 2)},
            population_size=6, generations=2, seed=42,
        )
        assert 8 <= result.best_params["fast"] <= 16
        assert result.best_params["fast"] < result.best_params["slow"]
