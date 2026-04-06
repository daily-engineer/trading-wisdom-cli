"""Paper trading (simulated execution) engine."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from trading_cli.core.order import (
    Account,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from trading_cli.core.risk import RiskCheckResult, RiskEngine


class PaperTrader:
    """Simulated trading engine for paper trading.

    Maintains an Account and processes orders against supplied prices.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
        risk_engine: Optional[RiskEngine] = None,
    ):
        self.account = Account(
            cash=initial_capital,
            initial_capital=initial_capital,
            commission_rate=commission_rate,
            slippage=slippage,
        )
        self.risk_engine = risk_engine or RiskEngine()
        self._order_counter = 0

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> Order:
        """Place a new order. Market orders are filled immediately."""
        self._order_counter += 1
        order = Order(
            id=f"ORD-{self._order_counter:05d}",
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
        )

        # For market orders, require current_price
        exec_price = current_price or price or 0
        if exec_price <= 0:
            order.status = OrderStatus.REJECTED
            order.message = "No execution price available"
            self.account.orders.append(order)
            return order

        # Risk check
        check = self.risk_engine.check_order(order, self.account, exec_price)
        if not check.passed:
            order.status = OrderStatus.REJECTED
            order.message = check.summary
            self.account.orders.append(order)
            return order

        # Execute immediately for market orders
        if order_type == OrderType.MARKET:
            self._execute_order(order, exec_price)
        else:
            # Limit/stop orders stay pending
            self.account.orders.append(order)

        return order

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        for order in self.account.orders:
            if order.id == order_id and order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                return True
        return False

    def close_position(self, symbol: str, current_price: float) -> Optional[Order]:
        """Close an entire position at current price."""
        symbol = symbol.upper()
        pos = self.account.positions.get(symbol)
        if not pos:
            return None
        return self.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=pos.quantity,
            current_price=current_price,
        )

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update position prices with latest market data."""
        for symbol, price in prices.items():
            symbol = symbol.upper()
            if symbol in self.account.positions:
                self.account.positions[symbol].current_price = price

    def check_risk(self) -> RiskCheckResult:
        """Run portfolio-level risk check."""
        return self.risk_engine.check_portfolio(self.account)

    def _execute_order(self, order: Order, exec_price: float) -> None:
        """Fill an order at the given price with slippage and commission."""
        if order.side == OrderSide.BUY:
            fill_price = exec_price * (1 + self.account.slippage)
            commission = fill_price * order.quantity * self.account.commission_rate
            total_cost = fill_price * order.quantity + commission

            order.filled_price = fill_price
            order.filled_quantity = order.quantity
            order.commission = commission
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now()

            self.account.cash -= total_cost

            # Update or create position
            if order.symbol in self.account.positions:
                pos = self.account.positions[order.symbol]
                total_qty = pos.quantity + order.quantity
                pos.avg_cost = (
                    pos.cost_basis + fill_price * order.quantity
                ) / total_qty
                pos.quantity = total_qty
                pos.current_price = exec_price
            else:
                self.account.positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    avg_cost=fill_price,
                    current_price=exec_price,
                )

        elif order.side == OrderSide.SELL:
            fill_price = exec_price * (1 - self.account.slippage)
            commission = fill_price * order.quantity * self.account.commission_rate
            proceeds = fill_price * order.quantity - commission

            order.filled_price = fill_price
            order.filled_quantity = order.quantity
            order.commission = commission
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now()

            self.account.cash += proceeds

            sell_pos = self.account.positions.get(order.symbol)
            if sell_pos is not None:
                sell_pos.quantity -= order.quantity
                if sell_pos.quantity <= 0:
                    del self.account.positions[order.symbol]

        self.account.orders.append(order)
