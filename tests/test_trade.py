"""Tests for the trading system — orders, risk, and paper trading."""

import pytest

from trading_cli.core.order import Account, Order, OrderSide, OrderStatus, OrderType, Position
from trading_cli.core.risk import RiskConfig, RiskEngine
from trading_cli.core.paper_trader import PaperTrader


class TestOrder:
    def test_order_defaults(self):
        o = Order(id="O1", symbol="TEST", side=OrderSide.BUY, quantity=100)
        assert o.status == OrderStatus.PENDING
        assert o.filled_quantity == 0
        assert o.order_type == OrderType.MARKET

    def test_position_pnl(self):
        p = Position(symbol="TEST", quantity=100, avg_cost=10.0, current_price=12.0)
        assert p.market_value == 1200.0
        assert p.unrealized_pnl == 200.0
        assert p.unrealized_pnl_pct == pytest.approx(20.0)

    def test_position_negative_pnl(self):
        p = Position(symbol="TEST", quantity=100, avg_cost=10.0, current_price=9.0)
        assert p.unrealized_pnl == -100.0

    def test_account_equity(self):
        a = Account(cash=50000, initial_capital=100000)
        a.positions["A"] = Position(symbol="A", quantity=100, avg_cost=10, current_price=12)
        assert a.total_market_value == 1200
        assert a.total_equity == 51200
        assert a.total_pnl == -48800

    def test_account_open_orders(self):
        a = Account()
        a.orders.append(Order(id="O1", symbol="A", side=OrderSide.BUY, quantity=100, status=OrderStatus.PENDING))
        a.orders.append(Order(id="O2", symbol="B", side=OrderSide.BUY, quantity=50, status=OrderStatus.FILLED))
        assert len(a.get_open_orders()) == 1
        assert len(a.get_filled_orders()) == 1


class TestRiskEngine:
    def test_buy_passes(self):
        engine = RiskEngine()
        account = Account(cash=100000, initial_capital=100000)
        order = Order(id="O1", symbol="A", side=OrderSide.BUY, quantity=100)
        result = engine.check_order(order, account, 10.0)
        assert result.passed

    def test_insufficient_cash(self):
        engine = RiskEngine()
        account = Account(cash=100, initial_capital=100000)
        order = Order(id="O1", symbol="A", side=OrderSide.BUY, quantity=100)
        result = engine.check_order(order, account, 10.0)
        assert not result.passed
        assert any("Insufficient cash" in v for v in result.violations)

    def test_max_positions(self):
        engine = RiskEngine(RiskConfig(max_positions=1))
        account = Account(cash=100000, initial_capital=100000)
        account.positions["B"] = Position(symbol="B", quantity=1, avg_cost=1, current_price=1)
        order = Order(id="O1", symbol="A", side=OrderSide.BUY, quantity=100)
        result = engine.check_order(order, account, 10.0)
        assert not result.passed

    def test_sell_no_position(self):
        engine = RiskEngine()
        account = Account(cash=100000, initial_capital=100000)
        order = Order(id="O1", symbol="A", side=OrderSide.SELL, quantity=100)
        result = engine.check_order(order, account, 10.0)
        assert not result.passed

    def test_portfolio_check_passes(self):
        engine = RiskEngine()
        account = Account(cash=100000, initial_capital=100000)
        result = engine.check_portfolio(account)
        assert result.passed

    def test_portfolio_daily_loss(self):
        engine = RiskEngine(RiskConfig(max_daily_loss_pct=5.0))
        account = Account(cash=90000, initial_capital=100000)
        # total_pnl_pct = -10%, exceeds limit
        result = engine.check_portfolio(account)
        assert not result.passed

    def test_max_shares(self):
        engine = RiskEngine(RiskConfig(max_position_pct=0.25, min_cash_reserve_pct=0.10))
        account = Account(cash=100000, initial_capital=100000)
        shares = engine.max_shares(account, 10.0)
        # max by concentration: 100000 * 0.25 = 25000 → 2500 shares
        # max by cash: 100000 - 10000 reserve = 90000 → 9000 shares
        assert shares == 2500

    def test_stop_loss(self):
        engine = RiskEngine(RiskConfig(max_single_loss_pct=3.0))
        assert engine.suggest_stop_loss(100.0) == pytest.approx(97.0)


class TestPaperTrader:
    def test_buy_and_check_account(self):
        trader = PaperTrader(initial_capital=100000)
        order = trader.place_order("TEST", OrderSide.BUY, 100, current_price=10.0)
        assert order.status == OrderStatus.FILLED
        assert trader.account.position_count == 1
        assert trader.account.cash < 100000

    def test_buy_then_sell(self):
        trader = PaperTrader(initial_capital=100000)
        trader.place_order("TEST", OrderSide.BUY, 100, current_price=10.0)
        sell = trader.place_order("TEST", OrderSide.SELL, 100, current_price=10.0)
        assert sell.status == OrderStatus.FILLED
        assert trader.account.position_count == 0

    def test_close_position(self):
        trader = PaperTrader(initial_capital=100000)
        trader.place_order("TEST", OrderSide.BUY, 100, current_price=10.0)
        order = trader.close_position("TEST", 11.0)
        assert order is not None
        assert order.status == OrderStatus.FILLED
        assert trader.account.position_count == 0
        # Should have profit (price went up)
        assert trader.account.cash > 99000

    def test_close_nonexistent(self):
        trader = PaperTrader()
        assert trader.close_position("NOPE", 10.0) is None

    def test_risk_rejection(self):
        trader = PaperTrader(initial_capital=1000)
        order = trader.place_order("TEST", OrderSide.BUY, 10000, current_price=10.0)
        assert order.status == OrderStatus.REJECTED

    def test_cancel_order(self):
        trader = PaperTrader()
        order = trader.place_order("TEST", OrderSide.BUY, 100,
                                   order_type=OrderType.LIMIT, price=5.0, current_price=10.0)
        # Limit orders stay pending
        assert order.status == OrderStatus.PENDING
        assert trader.cancel_order(order.id) is True

    def test_update_prices(self):
        trader = PaperTrader(initial_capital=100000)
        trader.place_order("TEST", OrderSide.BUY, 100, current_price=10.0)
        trader.update_prices({"TEST": 12.0})
        assert trader.account.positions["TEST"].current_price == 12.0

    def test_check_risk(self):
        trader = PaperTrader(initial_capital=100000)
        result = trader.check_risk()
        assert result.passed

    def test_add_to_existing_position(self):
        trader = PaperTrader(initial_capital=100000)
        trader.place_order("TEST", OrderSide.BUY, 100, current_price=10.0)
        trader.place_order("TEST", OrderSide.BUY, 100, current_price=12.0)
        pos = trader.account.positions["TEST"]
        assert pos.quantity == 200
        # avg_cost should be between 10 and 12 (with slippage)
        assert 10.0 < pos.avg_cost < 13.0
