"""Tests for market breadth & sentiment indicators.

Covers:
1.  normalize_ad_ratio   — boundary values
2.  normalize_turnover   — ratio boundaries
3.  normalize_northbound — flow boundaries and clamping
4.  normalize_limit_ratio — boundary values
5.  composite_sentiment_score — known inputs in expected range
6.  classify_sentiment   — boundary score values
7.  CLI: sentiment daily
8.  CLI: sentiment components
9.  CLI: sentiment regime
10. CLI: sentiment history --days 7
11. Score stability: ±10% noise → < 5-point score change
12. Edge cases: all zeros, all maximums, NaN/Inf inputs
"""

from __future__ import annotations

import math
import pytest

from click.testing import CliRunner

from trading_cli.core.sentiment import (
    WEIGHTS,
    advance_decline_ratio,
    classify_sentiment,
    composite_sentiment_score,
    gap_ratio,
    limit_up_down_count,
    normalize_ad_ratio,
    normalize_limit_ratio,
    normalize_northbound,
    normalize_turnover,
    northbound_flow,
    pct_above_ma,
    turnover_ratio,
)
from trading_cli.commands.sentiment_cmd import sentiment, _DEMO_INDICATORS

# ---------------------------------------------------------------------------
# 1. normalize_ad_ratio
# ---------------------------------------------------------------------------


class TestNormalizeAdRatio:
    def test_all_advancing(self) -> None:
        assert normalize_ad_ratio(100, 0) == pytest.approx(100.0)

    def test_all_declining(self) -> None:
        assert normalize_ad_ratio(0, 100) == pytest.approx(0.0)

    def test_equal(self) -> None:
        assert normalize_ad_ratio(50, 50) == pytest.approx(50.0)

    def test_both_zero(self) -> None:
        assert normalize_ad_ratio(0, 0) == pytest.approx(50.0)

    def test_partial(self) -> None:
        result = normalize_ad_ratio(75, 25)
        assert result == pytest.approx(75.0)

    def test_typical_values(self) -> None:
        result = normalize_ad_ratio(1850, 1200)
        # 1850/(1850+1200)*100 ≈ 60.65
        expected = 1850 / (1850 + 1200) * 100
        assert result == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# 2. normalize_turnover
# ---------------------------------------------------------------------------


class TestNormalizeTurnover:
    def test_ratio_one(self) -> None:
        assert normalize_turnover(1.0, 1.0) == pytest.approx(50.0)

    def test_ratio_two_capped(self) -> None:
        assert normalize_turnover(2.0, 1.0) == pytest.approx(100.0)

    def test_ratio_above_two_capped(self) -> None:
        # ratio > 2 should still cap at 100
        assert normalize_turnover(10.0, 1.0) == pytest.approx(100.0)

    def test_ratio_zero(self) -> None:
        assert normalize_turnover(0.0, 1.0) == pytest.approx(0.0)

    def test_avg_zero(self) -> None:
        assert normalize_turnover(1.0, 0.0) == pytest.approx(0.0)

    def test_half_ratio(self) -> None:
        assert normalize_turnover(0.5, 1.0) == pytest.approx(25.0)

    def test_typical(self) -> None:
        result = normalize_turnover(1.15, 1.0)
        assert 50.0 < result < 100.0


# ---------------------------------------------------------------------------
# 3. normalize_northbound
# ---------------------------------------------------------------------------


class TestNormalizeNorthbound:
    def test_plus_100(self) -> None:
        assert normalize_northbound(100.0) == pytest.approx(100.0)

    def test_minus_100(self) -> None:
        assert normalize_northbound(-100.0) == pytest.approx(0.0)

    def test_zero(self) -> None:
        assert normalize_northbound(0.0) == pytest.approx(50.0)

    def test_clamped_high(self) -> None:
        assert normalize_northbound(200.0) == pytest.approx(100.0)

    def test_clamped_low(self) -> None:
        assert normalize_northbound(-200.0) == pytest.approx(0.0)

    def test_plus_50(self) -> None:
        assert normalize_northbound(50.0) == pytest.approx(75.0)

    def test_minus_50(self) -> None:
        assert normalize_northbound(-50.0) == pytest.approx(25.0)

    def test_typical(self) -> None:
        result = normalize_northbound(23.5)
        assert 50.0 < result < 100.0


# ---------------------------------------------------------------------------
# 4. normalize_limit_ratio
# ---------------------------------------------------------------------------


class TestNormalizeLimitRatio:
    def test_all_up(self) -> None:
        assert normalize_limit_ratio(100, 0) == pytest.approx(100.0)

    def test_all_down(self) -> None:
        assert normalize_limit_ratio(0, 100) == pytest.approx(0.0)

    def test_equal(self) -> None:
        assert normalize_limit_ratio(50, 50) == pytest.approx(50.0)

    def test_both_zero(self) -> None:
        assert normalize_limit_ratio(0, 0) == pytest.approx(50.0)

    def test_typical(self) -> None:
        result = normalize_limit_ratio(45, 12)
        expected = 45 / (45 + 12) * 100
        assert result == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# 5. composite_sentiment_score — known inputs
# ---------------------------------------------------------------------------


class TestCompositeSentimentScore:
    def test_neutral_inputs(self) -> None:
        score = composite_sentiment_score(
            ad_ratio=50.0,
            pct_above_ma20=50.0,
            pct_above_ma60=50.0,
            turnover_current=1.0,
            turnover_avg=1.0,
            limit_up=50,
            limit_down=50,
            northbound_flow_val=0.0,
        )
        assert 40.0 <= score <= 60.0

    def test_bullish_inputs(self) -> None:
        score = composite_sentiment_score(
            ad_ratio=80.0,
            pct_above_ma20=80.0,
            pct_above_ma60=80.0,
            turnover_current=1.8,
            turnover_avg=1.0,
            limit_up=80,
            limit_down=10,
            northbound_flow_val=80.0,
        )
        assert score >= 60.0

    def test_bearish_inputs(self) -> None:
        score = composite_sentiment_score(
            ad_ratio=20.0,
            pct_above_ma20=15.0,
            pct_above_ma60=10.0,
            turnover_current=0.3,
            turnover_avg=1.0,
            limit_up=5,
            limit_down=80,
            northbound_flow_val=-80.0,
        )
        assert score <= 40.0

    def test_demo_indicators_range(self) -> None:
        ind = _DEMO_INDICATORS
        n_ad = normalize_ad_ratio(ind["advancing"], ind["declining"])
        score = composite_sentiment_score(
            ad_ratio=n_ad,
            pct_above_ma20=ind["pct_above_ma20"],
            pct_above_ma60=ind["pct_above_ma60"],
            turnover_current=ind["turnover_current"],
            turnover_avg=ind["turnover_avg"],
            limit_up=ind["limit_up"],
            limit_down=ind["limit_down"],
            northbound_flow_val=ind["northbound_flow"],
        )
        assert 0.0 <= score <= 100.0

    def test_score_bounded(self) -> None:
        # Maximum bullish
        score_max = composite_sentiment_score(
            ad_ratio=100.0,
            pct_above_ma20=100.0,
            pct_above_ma60=100.0,
            turnover_current=2.0,
            turnover_avg=1.0,
            limit_up=100,
            limit_down=0,
            northbound_flow_val=100.0,
        )
        assert score_max <= 100.0

        # Maximum bearish
        score_min = composite_sentiment_score(
            ad_ratio=0.0,
            pct_above_ma20=0.0,
            pct_above_ma60=0.0,
            turnover_current=0.0,
            turnover_avg=1.0,
            limit_up=0,
            limit_down=100,
            northbound_flow_val=-100.0,
        )
        assert score_min >= 0.0


# ---------------------------------------------------------------------------
# 6. classify_sentiment — boundary values
# ---------------------------------------------------------------------------


class TestClassifySentiment:
    def test_extreme_greed(self) -> None:
        label, _ = classify_sentiment(80.0)
        assert label == "极度贪婪"

    def test_above_80(self) -> None:
        label, _ = classify_sentiment(95.0)
        assert label == "极度贪婪"

    def test_optimistic_boundary(self) -> None:
        label, _ = classify_sentiment(60.0)
        assert label == "偏乐观"

    def test_optimistic_range(self) -> None:
        label, _ = classify_sentiment(70.0)
        assert label == "偏乐观"

    def test_neutral_boundary(self) -> None:
        label, _ = classify_sentiment(40.0)
        assert label == "中性"

    def test_neutral_range(self) -> None:
        label, _ = classify_sentiment(50.0)
        assert label == "中性"

    def test_pessimistic_boundary(self) -> None:
        label, _ = classify_sentiment(20.0)
        assert label == "偏悲观"

    def test_pessimistic_range(self) -> None:
        label, _ = classify_sentiment(30.0)
        assert label == "偏悲观"

    def test_extreme_fear(self) -> None:
        label, _ = classify_sentiment(10.0)
        assert label == "极度恐惧"

    def test_zero(self) -> None:
        label, _ = classify_sentiment(0.0)
        assert label == "极度恐惧"

    def test_action_hint_nonempty(self) -> None:
        for score in [5, 25, 45, 65, 85]:
            _, action = classify_sentiment(float(score))
            assert len(action) > 0


# ---------------------------------------------------------------------------
# 7-10. CLI commands
# ---------------------------------------------------------------------------


class TestSentimentCLI:
    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_daily_exit_code(self) -> None:
        result = self.runner.invoke(sentiment, ["daily"])
        assert result.exit_code == 0

    def test_daily_output_contains_score(self) -> None:
        result = self.runner.invoke(sentiment, ["daily"])
        output = result.output.lower()
        assert "sentiment" in output or any(c.isdigit() for c in output)

    def test_components_exit_code(self) -> None:
        result = self.runner.invoke(sentiment, ["components"])
        assert result.exit_code == 0

    def test_components_output_contains_weights(self) -> None:
        result = self.runner.invoke(sentiment, ["components"])
        # weight keywords should appear
        assert (
            "advance_decline" in result.output
            or "pct_above" in result.output
            or "20%" in result.output
        )

    def test_regime_exit_code(self) -> None:
        result = self.runner.invoke(sentiment, ["regime"])
        assert result.exit_code == 0

    def test_regime_output_contains_label(self) -> None:
        result = self.runner.invoke(sentiment, ["regime"])
        labels = ["极度贪婪", "偏乐观", "中性", "偏悲观", "极度恐惧"]
        assert any(label in result.output for label in labels)

    def test_history_exit_code(self) -> None:
        result = self.runner.invoke(sentiment, ["history", "--days", "7"])
        assert result.exit_code == 0

    def test_history_output_rows(self) -> None:
        result = self.runner.invoke(sentiment, ["history", "--days", "7"])
        # Should contain a sparkline line
        assert "Sparkline" in result.output or any(c.isdigit() for c in result.output)

    def test_help(self) -> None:
        result = self.runner.invoke(sentiment, ["--help"])
        assert result.exit_code == 0
        assert (
            "breadth" in result.output.lower() or "sentiment" in result.output.lower()
        )


# ---------------------------------------------------------------------------
# 11. Score stability: ±10% noise → < 5-point change
# ---------------------------------------------------------------------------


class TestScoreStability:
    def _base_score(self) -> float:
        ind = _DEMO_INDICATORS
        n_ad = normalize_ad_ratio(ind["advancing"], ind["declining"])
        return composite_sentiment_score(
            ad_ratio=n_ad,
            pct_above_ma20=ind["pct_above_ma20"],
            pct_above_ma60=ind["pct_above_ma60"],
            turnover_current=ind["turnover_current"],
            turnover_avg=ind["turnover_avg"],
            limit_up=ind["limit_up"],
            limit_down=ind["limit_down"],
            northbound_flow_val=ind["northbound_flow"],
        )

    def test_small_noise_minimal_score_change(self) -> None:
        base = self._base_score()
        # Apply 10% noise to each numeric indicator
        ind = _DEMO_INDICATORS
        noise = 0.10
        n_ad = normalize_ad_ratio(
            int(ind["advancing"] * (1 + noise)),
            int(ind["declining"] * (1 + noise)),
        )
        noisy_score = composite_sentiment_score(
            ad_ratio=n_ad,
            pct_above_ma20=ind["pct_above_ma20"] * (1 + noise),
            pct_above_ma60=ind["pct_above_ma60"] * (1 + noise),
            turnover_current=ind["turnover_current"] * (1 + noise),
            turnover_avg=ind["turnover_avg"],
            limit_up=int(ind["limit_up"] * (1 + noise)),
            limit_down=ind["limit_down"],
            northbound_flow_val=ind["northbound_flow"] * (1 + noise),
        )
        assert abs(noisy_score - base) < 5.0


# ---------------------------------------------------------------------------
# 12. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_all_zeros(self) -> None:
        score = composite_sentiment_score(
            ad_ratio=0.0,
            pct_above_ma20=0.0,
            pct_above_ma60=0.0,
            turnover_current=0.0,
            turnover_avg=0.0,
            limit_up=0,
            limit_down=0,
            northbound_flow_val=0.0,
        )
        assert 0.0 <= score <= 100.0

    def test_all_maximums(self) -> None:
        score = composite_sentiment_score(
            ad_ratio=100.0,
            pct_above_ma20=100.0,
            pct_above_ma60=100.0,
            turnover_current=2.0,
            turnover_avg=1.0,
            limit_up=100,
            limit_down=0,
            northbound_flow_val=100.0,
        )
        assert score == pytest.approx(100.0)

    def test_nan_ad_ratio_handled(self) -> None:
        score = composite_sentiment_score(
            ad_ratio=float("nan"),
            pct_above_ma20=50.0,
            pct_above_ma60=50.0,
            turnover_current=1.0,
            turnover_avg=1.0,
            limit_up=50,
            limit_down=50,
            northbound_flow_val=0.0,
        )
        assert not math.isnan(score)
        assert 0.0 <= score <= 100.0

    def test_inf_northbound_clamped(self) -> None:
        score = composite_sentiment_score(
            ad_ratio=50.0,
            pct_above_ma20=50.0,
            pct_above_ma60=50.0,
            turnover_current=1.0,
            turnover_avg=1.0,
            limit_up=50,
            limit_down=50,
            northbound_flow_val=float("inf"),
        )
        assert not math.isnan(score)
        assert 0.0 <= score <= 100.0

    def test_northbound_flow_unavailable(self) -> None:
        assert northbound_flow(None) == pytest.approx(0.0)

    def test_northbound_flow_value(self) -> None:
        assert northbound_flow(23.5) == pytest.approx(23.5)

    def test_weights_sum_to_one(self) -> None:
        total = sum(WEIGHTS.values())
        assert total == pytest.approx(1.0, rel=1e-6)
