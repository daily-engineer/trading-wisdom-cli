"""Tests for the monitoring system."""

import pandas as pd
import pytest

from trading_cli.core.monitor import (
    AlertCondition,
    AlertManager,
    AlertRule,
    MarketSnapshot,
)


class TestAlertRule:
    def test_price_above_triggers(self):
        rule = AlertRule(
            id="test-001", symbol="000001.SZ",
            condition=AlertCondition.PRICE_ABOVE, threshold=11.0,
        )
        assert rule.check({"close": 11.5}) is True
        assert rule.triggered is True

    def test_price_below_triggers(self):
        rule = AlertRule(
            id="test-002", symbol="000001.SZ",
            condition=AlertCondition.PRICE_BELOW, threshold=10.0,
        )
        assert rule.check({"close": 9.8}) is True

    def test_no_trigger_when_threshold_not_met(self):
        rule = AlertRule(
            id="test-003", symbol="000001.SZ",
            condition=AlertCondition.PRICE_ABOVE, threshold=15.0,
        )
        assert rule.check({"close": 11.0}) is False
        assert rule.triggered is False

    def test_already_triggered_does_not_re_trigger(self):
        rule = AlertRule(
            id="test-004", symbol="000001.SZ",
            condition=AlertCondition.PRICE_ABOVE, threshold=10.0,
            triggered=True,
        )
        assert rule.check({"close": 11.0}) is True
        # triggered_at should not update since it was already triggered

    def test_volume_above(self):
        rule = AlertRule(
            id="test-005", symbol="000001.SZ",
            condition=AlertCondition.VOLUME_ABOVE, threshold=1000000,
        )
        assert rule.check({"vol": 1500000}) is True

    def test_rsi_below(self):
        rule = AlertRule(
            id="test-006", symbol="000001.SZ",
            condition=AlertCondition.RSI_BELOW, threshold=30,
        )
        assert rule.check({"rsi": 25}) is True
        assert rule.check({"rsi": 35}) is False


class TestAlertManager:
    def test_add_and_list(self):
        mgr = AlertManager()
        rule = mgr.add_rule("000001.SZ", AlertCondition.PRICE_ABOVE, 12.0)
        assert rule.id == "alert-001"
        assert len(mgr.list_rules()) == 1

    def test_remove_rule(self):
        mgr = AlertManager()
        rule = mgr.add_rule("000001.SZ", AlertCondition.PRICE_ABOVE, 12.0)
        assert mgr.remove_rule(rule.id) is True
        assert len(mgr.list_rules()) == 0

    def test_remove_nonexistent(self):
        mgr = AlertManager()
        assert mgr.remove_rule("nonexistent") is False

    def test_check_all(self):
        mgr = AlertManager()
        mgr.add_rule("000001.SZ", AlertCondition.PRICE_ABOVE, 11.0)
        mgr.add_rule("000001.SZ", AlertCondition.PRICE_BELOW, 9.0)
        triggered = mgr.check_all("000001.SZ", {"close": 11.5})
        assert len(triggered) == 1
        assert triggered[0].condition == AlertCondition.PRICE_ABOVE

    def test_filter_by_symbol(self):
        mgr = AlertManager()
        mgr.add_rule("000001.SZ", AlertCondition.PRICE_ABOVE, 11.0)
        mgr.add_rule("600519.SH", AlertCondition.PRICE_ABOVE, 1800.0)
        assert len(mgr.list_rules("000001.SZ")) == 1

    def test_clear_triggered(self):
        mgr = AlertManager()
        mgr.add_rule("000001.SZ", AlertCondition.PRICE_ABOVE, 10.0)
        mgr.check_all("000001.SZ", {"close": 11.0})
        assert mgr.clear_triggered() == 1


class TestMarketSnapshot:
    def test_from_dataframe_row(self):
        row = pd.Series({"close": 11.12, "open": 11.28, "high": 11.28, "low": 11.09, "vol": 757757, "amount": 845000})
        snap = MarketSnapshot.from_dataframe_row("000001.SZ", row, prev_close=11.27)
        assert snap.symbol == "000001.SZ"
        assert snap.close == 11.12
        assert snap.change_pct < 0  # dropped from 11.27

    def test_change_pct_positive(self):
        row = pd.Series({"close": 11.50, "open": 11.00, "high": 11.60, "low": 10.90, "vol": 500000, "amount": 0})
        snap = MarketSnapshot.from_dataframe_row("TEST", row, prev_close=11.00)
        assert snap.change_pct > 0
