"""Backtesting engine for strategy evaluation."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional
import pandas as pd
import numpy as np

from trading_cli.strategy.models import (
    Signal,
    SignalType,
    Position,
    PositionType,
    Strategy,
    StrategyConfig,
    StrategyResult,
)


class BacktestEngine:
    """Backtesting engine for strategy evaluation."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission_rate: float = 0.0003,
        slippage: float = 0.001,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage

        # State
        self.capital = initial_capital
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.trades: list[dict] = []
        self.equity_curve: list[float] = []

        # Metrics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

    def reset(self):
        """Reset engine state."""
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.equity_curve = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0

    def run(
        self, strategy: Strategy, data: pd.DataFrame, symbol: str
    ) -> StrategyResult:
        """Run backtest on historical data.

        Args:
            strategy: Strategy instance to test
            data: Historical OHLCV data
            symbol: Stock symbol

        Returns:
            StrategyResult with performance metrics
        """
        start_time = time.time()
        self.reset()

        # Prepare data
        data = data.copy()
        data["symbol"] = symbol

        signals = []
        equity_start = self.initial_capital

        # Iterate through data
        for i in range(len(data)):
            current_data = data.iloc[: i + 1].to_dict("list")

            # Generate signal
            signal = strategy.generate_signal(current_data)
            signals.append(signal)

            # Update positions with current price
            current_price = data["close"].iloc[i]
            self._update_positions(current_price)

            # Process signal
            if signal.signal_type == SignalType.BUY:
                self._execute_buy(signal, current_price, strategy.config)
            elif signal.signal_type == SignalType.SELL:
                self._execute_sell(signal, current_price)

            # Record equity
            current_equity = self._calculate_equity(current_price)
            self.equity_curve.append(current_equity)

        # Close any open positions at the end
        final_price = data["close"].iloc[-1]
        self._close_all_positions(final_price)

        # Calculate metrics
        execution_time = time.time() - start_time

        return self._calculate_results(
            strategy, symbol, signals, execution_time, equity_start, final_price
        )

    def _execute_buy(self, signal: Signal, price: float, config: StrategyConfig):
        """Execute a buy order."""
        # Apply slippage
        buy_price = price * (1 + self.slippage)

        # Calculate position size
        position_value = self.capital * config.position_size
        shares = int(position_value / buy_price)

        if shares <= 0 or self.capital < buy_price * shares:
            return

        # Check max positions
        if len(self.positions) >= config.max_positions:
            return

        # Calculate commission
        commission = buy_price * shares * self.commission_rate

        # Execute
        self.capital -= buy_price * shares + commission

        self.positions[signal.symbol] = Position(
            symbol=signal.symbol,
            position_type=PositionType.LONG,
            quantity=shares,
            entry_price=buy_price,
            current_price=buy_price,
            entry_date=datetime.now(),
        )

        self.trades.append(
            {
                "symbol": signal.symbol,
                "type": "BUY",
                "price": buy_price,
                "quantity": shares,
                "commission": commission,
                "timestamp": signal.timestamp,
            }
        )
        self.total_trades += 1

    def _execute_sell(self, signal: Signal, price: float):
        """Execute a sell order (close position)."""
        if signal.symbol not in self.positions:
            return

        position = self.positions[signal.symbol]

        # Apply slippage
        sell_price = price * (1 - self.slippage)

        # Calculate P&L
        pnl = (sell_price - position.entry_price) * position.quantity
        commission = sell_price * position.quantity * self.commission_rate
        net_pnl = pnl - commission

        # Execute
        self.capital += sell_price * position.quantity - commission

        self.trades.append(
            {
                "symbol": signal.symbol,
                "type": "SELL",
                "price": sell_price,
                "quantity": position.quantity,
                "commission": commission,
                "pnl": net_pnl,
                "timestamp": signal.timestamp,
            }
        )

        if net_pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        del self.positions[signal.symbol]

    def _close_all_positions(self, price: float):
        """Close all open positions at current price."""
        for symbol in list(self.positions.keys()):
            signal = Signal(symbol=symbol, signal_type=SignalType.CLOSE, price=price)
            self._execute_sell(signal, price)

    def _update_positions(self, current_price: float):
        """Update position values with current price."""
        for pos in self.positions.values():
            pos.current_price = current_price
            pos.pnl = (current_price - pos.entry_price) * pos.quantity
            pos.pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100

    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current total equity."""
        positions_value = sum(
            pos.current_price * pos.quantity for pos in self.positions.values()
        )
        return self.capital + positions_value

    def _calculate_results(
        self,
        strategy: Strategy,
        symbol: str,
        signals: list[Signal],
        execution_time: float,
        equity_start: float,
        final_price: float,
    ) -> StrategyResult:
        """Calculate final performance metrics."""
        equity_curve = pd.Series(self.equity_curve)

        # Returns
        total_return = self.capital - self.initial_capital
        total_return_pct = (
            (self.capital - self.initial_capital) / self.initial_capital * 100
        )

        # Win rate
        win_rate = (
            self.winning_trades / self.total_trades * 100
            if self.total_trades > 0
            else 0
        )

        # Max drawdown
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax * 100
        max_drawdown = drawdown.min()

        # Sharpe ratio (simplified)
        if len(equity_curve) > 1:
            returns = equity_curve.pct_change().dropna()
            sharpe = (
                returns.mean() / returns.std() * np.sqrt(252)
                if returns.std() > 0
                else 0
            )
        else:
            sharpe = 0

        return StrategyResult(
            strategy_name=strategy.config.name,
            symbol=symbol,
            signals=signals,
            positions=list(self.positions.values()),
            total_trades=self.total_trades,
            winning_trades=self.winning_trades,
            losing_trades=self.losing_trades,
            win_rate=win_rate,
            total_pnl=total_return,
            total_pnl_pct=total_return_pct,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            execution_time=execution_time,
        )
