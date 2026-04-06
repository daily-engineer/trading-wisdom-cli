"""Order and account models for the trading system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Order(BaseModel):
    """A single trading order."""

    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: int
    price: Optional[float] = None          # limit / stop-limit price
    stop_price: Optional[float] = None     # stop trigger price
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    filled_price: float = 0.0
    commission: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None
    message: str = ""


class Position(BaseModel):
    """An open position in the account."""

    symbol: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    market: str = "CN"

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        return (self.unrealized_pnl / self.cost_basis * 100) if self.cost_basis else 0.0


class Account(BaseModel):
    """Trading account state."""

    account_id: str = "paper-001"
    cash: float = 100000.0
    initial_capital: float = 100000.0
    positions: dict[str, Position] = Field(default_factory=dict)
    orders: list[Order] = Field(default_factory=list)
    commission_rate: float = 0.0003
    slippage: float = 0.001

    @property
    def total_market_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def total_equity(self) -> float:
        return self.cash + self.total_market_value

    @property
    def total_pnl(self) -> float:
        return self.total_equity - self.initial_capital

    @property
    def total_pnl_pct(self) -> float:
        return (self.total_pnl / self.initial_capital * 100) if self.initial_capital else 0.0

    @property
    def position_count(self) -> int:
        return len(self.positions)

    def get_open_orders(self) -> list[Order]:
        return [o for o in self.orders if o.status == OrderStatus.PENDING]

    def get_filled_orders(self) -> list[Order]:
        return [o for o in self.orders if o.status == OrderStatus.FILLED]
