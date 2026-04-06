"""Abstract base class for all trader implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from trading_cli.core.order import Order, OrderSide, OrderType
from trading_cli.core.risk import RiskCheckResult


class BaseTrader(ABC):
    """Common interface for paper and live trading engines."""

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> Order: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def close_position(self, symbol: str, current_price: float) -> Optional[Order]: ...

    @abstractmethod
    def emergency_stop(self, prices: dict[str, float]) -> list[Order]: ...

    @abstractmethod
    def check_risk(self) -> RiskCheckResult: ...
