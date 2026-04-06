"""Tests for RealTrader and TradeLogger — all ib_insync calls are mocked."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock
from pathlib import Path

import pytest

from trading_cli.core.order import Order, OrderSide, OrderStatus, OrderType
from trading_cli.core.trade_logger import TradeLogger


class TestTradeLogger:
    def test_log_writes_correct_fields(self, tmp_path):
        log_file = tmp_path / "trade_log.jsonl"
        logger = TradeLogger(log_path=log_file)

        order = Order(
            id="LIVE-00001",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            status=OrderStatus.FILLED,
            filled_price=185.10,
            filled_quantity=100,
        )
        logger.log(order, mode="live", account_id="U1234567")

        entries = [json.loads(line) for line in log_file.read_text().splitlines()]
        assert len(entries) == 1
        e = entries[0]
        assert e["symbol"] == "AAPL"
        assert e["side"] == "BUY"
        assert e["quantity"] == 100
        assert e["filled_price"] == pytest.approx(185.10)
        assert e["status"] == "FILLED"
        assert e["mode"] == "live"
        assert e["order_id"] == "LIVE-00001"
        assert e["account_id_suffix"] == "4567"

    def test_log_no_token_leakage(self, tmp_path):
        log_file = tmp_path / "trade_log.jsonl"
        logger = TradeLogger(log_path=log_file)

        order = Order(
            id="LIVE-00002",
            symbol="MSFT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=50,
            status=OrderStatus.FILLED,
            filled_price=420.0,
            filled_quantity=50,
        )
        logger.log(order, mode="live", account_id="token_secret_password")

        raw = log_file.read_text()
        assert "token_secret_password" not in raw
        assert "secret" not in raw
        # account_id_suffix should only be last 4 chars
        entry = json.loads(raw.strip())
        assert entry["account_id_suffix"] == "word"  # last 4 of "token_secret_password"


from trading_cli.core.live_trader import RealTrader


def _make_mock_ib_module():
    """Return (mock_module, mock_ib_instance) with sensible defaults."""
    ib_instance = MagicMock()
    ib_instance.isConnected.return_value = True
    ib_instance.positions.return_value = []
    mock_mod = MagicMock()
    mock_mod.IB.return_value = ib_instance
    return mock_mod, ib_instance


def _filled_trade(price: float = 100.0, qty: float = 100.0) -> MagicMock:
    t = MagicMock()
    t.orderStatus.status = "Filled"
    t.orderStatus.avgFillPrice = price
    t.orderStatus.filled = qty
    return t


def _pending_trade() -> MagicMock:
    t = MagicMock()
    t.orderStatus.status = "Submitted"
    t.orderStatus.avgFillPrice = 0.0
    t.orderStatus.filled = 0.0
    return t


def _inactive_trade() -> MagicMock:
    t = MagicMock()
    t.orderStatus.status = "Inactive"
    t.orderStatus.avgFillPrice = 0.0
    t.orderStatus.filled = 0.0
    return t


@pytest.fixture
def mock_ib(monkeypatch):
    """Inject a mock ib_insync module and return (mock_module, ib_instance)."""
    mock_mod, ib_instance = _make_mock_ib_module()
    monkeypatch.setitem(sys.modules, "ib_insync", mock_mod)
    return mock_mod, ib_instance


class TestRealTrader:
    def test_place_order_buy_filled(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _filled_trade(185.10, 100.0)

        trader = RealTrader()
        order = trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)

        assert order.status == OrderStatus.FILLED
        assert order.filled_price == pytest.approx(185.10)
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY

    def test_place_order_sell_filled(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _filled_trade(185.0, 100.0)

        trader = RealTrader()
        order = trader.place_order("AAPL", OrderSide.SELL, 100, current_price=185.0)

        assert order.status == OrderStatus.FILLED
        assert order.side == OrderSide.SELL

    def test_place_order_rejected(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _inactive_trade()

        trader = RealTrader()
        order = trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)

        assert order.status == OrderStatus.REJECTED

    def test_cancel_order_success(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _pending_trade()

        trader = RealTrader()
        order = trader.place_order(
            "AAPL", OrderSide.BUY, 100, order_type=OrderType.LIMIT, price=184.0
        )
        result = trader.cancel_order(order.id)

        assert result is True
        ib.cancelOrder.assert_called_once()

    def test_cancel_order_not_found(self, mock_ib):
        _, _ = mock_ib
        trader = RealTrader()
        assert trader.cancel_order("NONEXISTENT") is False

    def test_close_position_with_holding(self, mock_ib):
        mock_mod, ib = mock_ib
        pos_mock = MagicMock()
        pos_mock.contract.symbol = "AAPL"
        pos_mock.position = 100.0
        ib.positions.return_value = [pos_mock]
        ib.placeOrder.return_value = _filled_trade(185.0, 100.0)

        trader = RealTrader()
        order = trader.close_position("AAPL", 185.0)

        assert order is not None
        assert order.side == OrderSide.SELL
        assert order.quantity == 100

    def test_close_position_no_holding(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.positions.return_value = []

        trader = RealTrader()
        order = trader.close_position("AAPL", 185.0)

        assert order is None

    def test_emergency_stop_cancels_then_closes(self, mock_ib):
        mock_mod, ib = mock_ib
        pos_mock = MagicMock()
        pos_mock.contract.symbol = "AAPL"
        pos_mock.position = 100.0
        ib.positions.return_value = [pos_mock]
        ib.placeOrder.return_value = _filled_trade(185.0, 100.0)

        trader = RealTrader()
        orders = trader.emergency_stop({"AAPL": 185.0})

        ib.reqGlobalCancel.assert_called_once()
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL

    def test_emergency_stop_no_positions(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.positions.return_value = []

        trader = RealTrader()
        orders = trader.emergency_stop({})

        ib.reqGlobalCancel.assert_called_once()
        assert orders == []

    def test_ib_not_installed_raises(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "ib_insync", None)

        trader = RealTrader()
        with pytest.raises(RuntimeError, match="ib_insync is required"):
            trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)

    def test_check_risk_disconnected(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.isConnected.return_value = False

        trader = RealTrader()
        result = trader.check_risk()

        assert not result.passed
        assert any("not connected" in v.lower() for v in result.violations)

    def test_connection_failure_raises(self, monkeypatch):
        mock_mod = MagicMock()
        mock_mod.IB.return_value.connect.side_effect = OSError("Connection refused")
        monkeypatch.setitem(sys.modules, "ib_insync", mock_mod)

        trader = RealTrader()
        with pytest.raises(RuntimeError, match="Failed to connect"):
            trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)
