# trading_cli/core/live_trader.py
"""Live trading engine backed by Interactive Brokers via ib_insync."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from trading_cli.core.base_trader import BaseTrader
from trading_cli.core.market import detect_market
from trading_cli.core.order import Order, OrderSide, OrderStatus, OrderType
from trading_cli.core.risk import RiskCheckResult, RiskEngine
from trading_cli.core.trade_logger import TradeLogger


class RealTrader(BaseTrader):
    """Live IBKR trading engine.

    Connects to IB TWS/Gateway via ib_insync (lazy connection on first use).
    Credentials are read from environment variables: IB_HOST, IB_PORT, IB_CLIENT_ID.
    """

    def __init__(
        self,
        host: str = "",
        port: int = 0,
        client_id: int = 0,
        fill_timeout: float = 10.0,
        logger: Optional[TradeLogger] = None,
        account_id: str = "",
    ):
        self._host = host or os.environ.get("IB_HOST", "127.0.0.1")
        self._port = port or int(os.environ.get("IB_PORT", "7497"))
        self._client_id = client_id or int(os.environ.get("IB_CLIENT_ID", "1"))
        self._fill_timeout = fill_timeout
        self._ib: Optional[Any] = None
        self._trades: dict[str, Any] = {}  # order_id -> ib_insync.Trade
        self._order_counter = 0
        self.logger = logger or TradeLogger()
        self._account_id = account_id
        self._risk_engine = RiskEngine()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_ib(self) -> Any:
        """Lazy-connect to IB TWS/Gateway."""
        if self._ib is None:
            try:
                from ib_insync import IB

                self._ib = IB()
                self._ib.connect(self._host, self._port, clientId=self._client_id)
            except ImportError:
                raise RuntimeError(
                    "ib_insync is required for live trading. "
                    "Install with: pip install ib_insync"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to connect to IB TWS/Gateway: {e}")
        return self._ib

    def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            self._ib = None

    # ------------------------------------------------------------------
    # Contract helpers
    # ------------------------------------------------------------------

    def _build_contract(self, symbol: str) -> Any:
        from ib_insync import Stock

        mkt = detect_market(symbol.upper())
        if mkt == "HK":
            return Stock(symbol.upper().replace(".HK", ""), "SEHK", "HKD")
        return Stock(symbol.upper().split(".")[0], "SMART", "USD")

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"LIVE-{self._order_counter:05d}"

    def _map_status(self, ib_status: str) -> OrderStatus:
        return {
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.REJECTED,
        }.get(ib_status, OrderStatus.PENDING)

    def _get_position_qty(self, symbol: str) -> int:
        ib = self._get_ib()
        clean = symbol.upper().replace(".HK", "").split(".")[0]
        for pos in ib.positions():
            if pos.contract.symbol == clean:
                return int(pos.position)
        return 0

    # ------------------------------------------------------------------
    # BaseTrader interface
    # ------------------------------------------------------------------

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
        ib = self._get_ib()
        from ib_insync import LimitOrder, MarketOrder

        contract = self._build_contract(symbol)
        ib.qualifyContracts(contract)

        ib_action = "BUY" if side == OrderSide.BUY else "SELL"
        if order_type == OrderType.LIMIT and price:
            ib_order = LimitOrder(ib_action, quantity, price)
        else:
            ib_order = MarketOrder(ib_action, quantity)

        order_id = self._next_order_id()
        trade = ib.placeOrder(contract, ib_order)
        self._trades[order_id] = trade

        ib.sleep(self._fill_timeout)

        status = self._map_status(trade.orderStatus.status)
        filled_price = float(trade.orderStatus.avgFillPrice or 0.0)
        filled_qty = int(trade.orderStatus.filled or 0)

        order = Order(
            id=order_id,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=status,
            filled_quantity=filled_qty,
            filled_price=filled_price,
            filled_at=datetime.now() if status == OrderStatus.FILLED else None,
        )

        self.logger.log(order, mode="live", account_id=self._account_id)
        return order

    def cancel_order(self, order_id: str) -> bool:
        trade = self._trades.get(order_id)
        if not trade:
            return False
        try:
            ib = self._get_ib()
            ib.cancelOrder(trade.order)
            ib.sleep(1.0)
            return True
        except Exception:
            return False

    def close_position(self, symbol: str, current_price: float) -> Optional[Order]:
        qty = self._get_position_qty(symbol)
        if qty <= 0:
            return None
        return self.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=qty,
            current_price=current_price,
        )

    def emergency_stop(self, prices: dict[str, float]) -> list[Order]:
        """Cancel all open orders then market-sell all IB positions."""
        ib = self._get_ib()
        orders: list[Order] = []

        # Step 1: cancel everything
        ib.reqGlobalCancel()
        ib.sleep(1.0)

        # Step 2: close all positions
        for pos in ib.positions():
            qty = int(pos.position)
            if qty <= 0:
                continue
            symbol = pos.contract.symbol
            price = prices.get(symbol, 0.0)
            order = self.place_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=qty,
                current_price=price,
            )
            orders.append(order)

        return orders

    def check_risk(self) -> RiskCheckResult:
        try:
            ib = self._get_ib()
            if not ib.isConnected():
                return RiskCheckResult(passed=False, violations=["IB not connected"])
            return RiskCheckResult(passed=True, violations=[])
        except Exception as e:
            return RiskCheckResult(passed=False, violations=[str(e)])
