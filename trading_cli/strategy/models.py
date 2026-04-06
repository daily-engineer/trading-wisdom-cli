"""Strategy models and definitions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """Trading signal types."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"  # Close position


class PositionType(str, Enum):
    """Position direction."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class Signal(BaseModel):
    """Trading signal model."""

    symbol: str
    signal_type: SignalType
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    price: Optional[float] = None
    quantity: Optional[int] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Position(BaseModel):
    """Position model."""

    symbol: str
    position_type: PositionType
    quantity: int = 0
    entry_price: float = 0.0
    current_price: float = 0.0
    entry_date: Optional[datetime] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0


class StrategyConfig(BaseModel):
    """Base strategy configuration."""

    name: str
    description: str = ""
    enabled: bool = True

    # Risk parameters
    position_size: float = 1.0  # 0-1, percentage of capital
    max_positions: int = 5
    stop_loss_pct: float = 5.0  # Stop loss percentage
    take_profit_pct: float = 10.0  # Take profit percentage

    # Execution parameters
    commission_rate: float = 0.0003  # 0.03%
    slippage: float = 0.001  # 0.1%


class StrategyResult(BaseModel):
    """Strategy execution result."""

    strategy_name: str
    symbol: str
    signals: list[Signal] = Field(default_factory=list)
    positions: list[Position] = Field(default_factory=list)

    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    execution_time: float = 0.0  # seconds


class Strategy:
    """Trading strategy definition (base class)."""

    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig(name="base")
        self.parameters: dict[str, Any] = {}

    def generate_signal(self, data: dict) -> Signal:
        """Generate trading signal from market data.

        Args:
            data: Market data dictionary with OHLCV columns

        Returns:
            Signal object
        """
        raise NotImplementedError("Subclasses must implement generate_signal")

    def validate_params(self) -> bool:
        """Validate strategy parameters."""
        return True
