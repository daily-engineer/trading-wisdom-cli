"""Built-in trading strategies."""

from __future__ import annotations

from typing import Any
import pandas as pd

from trading_cli.strategy.models import (
    Signal, SignalType, Strategy, StrategyConfig, PositionType
)
from trading_cli.core.indicators import TechnicalIndicators


class MAStrategy(Strategy):
    """Moving Average Crossover Strategy."""
    
    def __init__(self, config: StrategyConfig = None, **params):
        super().__init__()
        self.config = config or StrategyConfig(name="ma_cross")
        self.parameters = {
            "fast_period": 10,
            "slow_period": 30,
            **params
        }
    
    def generate_signal(self, data: dict) -> Signal:
        """Generate signal based on MA crossover."""
        df = pd.DataFrame(data)
        if len(df) < self.parameters["slow_period"] + 1:
            return Signal(symbol=df["symbol"].iloc[-1], signal_type=SignalType.HOLD)
        
        fast = TechnicalIndicators.ema(
            df["close"], 
            self.parameters["fast_period"]
        )
        slow = TechnicalIndicators.ema(
            df["close"], 
            self.parameters["slow_period"]
        )
        
        current_fast = fast.iloc[-1]
        current_slow = slow.iloc[-1]
        prev_fast = fast.iloc[-2]
        prev_slow = slow.iloc[-2]
        
        symbol = df["symbol"].iloc[-1]
        price = df["close"].iloc[-1]
        
        # Golden cross (bullish)
        if prev_fast <= prev_slow and current_fast > current_slow:
            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=price,
                strength=0.8,
                metadata={"strategy": "MA_CROSS", "type": "GOLDEN_CROSS"}
            )
        
        # Death cross (bearish)
        if prev_fast >= prev_slow and current_fast < current_slow:
            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=price,
                strength=0.8,
                metadata={"strategy": "MA_CROSS", "type": "DEATH_CROSS"}
            )
        
        return Signal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            price=price,
            metadata={"strategy": "MA_CROSS"}
        )


class RSIStrategy(Strategy):
    """RSI Mean Reversion Strategy."""
    
    def __init__(self, config: StrategyConfig = None, **params):
        super().__init__()
        self.config = config or StrategyConfig(name="rsi")
        self.parameters = {
            "period": 14,
            "oversold": 30,
            "overbought": 70,
            **params
        }
    
    def generate_signal(self, data: dict) -> Signal:
        """Generate signal based on RSI levels."""
        df = pd.DataFrame(data)
        if len(df) < self.parameters["period"] + 1:
            return Signal(symbol=df["symbol"].iloc[-1], signal_type=SignalType.HOLD)
        
        rsi = TechnicalIndicators.rsi(df["close"], self.parameters["period"])
        current_rsi = rsi.iloc[-1]
        
        symbol = df["symbol"].iloc[-1]
        price = df["close"].iloc[-1]
        
        # Oversold - potential buy
        if current_rsi < self.parameters["oversold"]:
            strength = (self.parameters["oversold"] - current_rsi) / self.parameters["oversold"]
            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=price,
                strength=min(strength, 1.0),
                metadata={"strategy": "RSI", "rsi": current_rsi, "level": "OVERSOLD"}
            )
        
        # Overbought - potential sell
        if current_rsi > self.parameters["overbought"]:
            strength = (current_rsi - self.parameters["overbought"]) / (100 - self.parameters["overbought"])
            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=price,
                strength=min(strength, 1.0),
                metadata={"strategy": "RSI", "rsi": current_rsi, "level": "OVERBOUGHT"}
            )
        
        return Signal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            price=price,
            metadata={"strategy": "RSI", "rsi": current_rsi}
        )


class MACDStrategy(Strategy):
    """MACD Strategy."""
    
    def __init__(self, config: StrategyConfig = None, **params):
        super().__init__()
        self.config = config or StrategyConfig(name="macd")
        self.parameters = {
            "fast": 12,
            "slow": 26,
            "signal": 9,
            **params
        }
    
    def generate_signal(self, data: dict) -> Signal:
        """Generate signal based on MACD crossover."""
        df = pd.DataFrame(data)
        if len(df) < self.parameters["slow"] + 1:
            return Signal(symbol=df["symbol"].iloc[-1], signal_type=SignalType.HOLD)
        
        macd, signal, hist = TechnicalIndicators.macd(
            df["close"],
            self.parameters["fast"],
            self.parameters["slow"],
            self.parameters["signal"]
        )
        
        current_hist = hist.iloc[-1]
        prev_hist = hist.iloc[-2]
        
        symbol = df["symbol"].iloc[-1]
        price = df["close"].iloc[-1]
        
        # Bullish crossover
        if prev_hist <= 0 and current_hist > 0:
            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=price,
                strength=min(abs(current_hist) * 10, 1.0),
                metadata={"strategy": "MACD", "histogram": current_hist}
            )
        
        # Bearish crossover
        if prev_hist >= 0 and current_hist < 0:
            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=price,
                strength=min(abs(current_hist) * 10, 1.0),
                metadata={"strategy": "MACD", "histogram": current_hist}
            )
        
        return Signal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            price=price,
            metadata={"strategy": "MACD", "histogram": current_hist}
        )


class BollingerStrategy(Strategy):
    """Bollinger Bands Mean Reversion Strategy."""
    
    def __init__(self, config: StrategyConfig = None, **params):
        super().__init__()
        self.config = config or StrategyConfig(name="bollinger")
        self.parameters = {
            "period": 20,
            "std_dev": 2.0,
            **params
        }
    
    def generate_signal(self, data: dict) -> Signal:
        """Generate signal based on Bollinger Bands."""
        df = pd.DataFrame(data)
        if len(df) < self.parameters["period"] + 1:
            return Signal(symbol=df["symbol"].iloc[-1], signal_type=SignalType.HOLD)
        
        upper, middle, lower = TechnicalIndicators.bollinger_bands(
            df["close"],
            self.parameters["period"],
            self.parameters["std_dev"]
        )
        
        current_price = df["close"].iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        current_middle = middle.iloc[-1]
        
        # Calculate position within bands (0 = at lower, 1 = at upper)
        band_width = current_upper - current_lower
        position = (current_price - current_lower) / band_width if band_width > 0 else 0.5
        
        symbol = df["symbol"].iloc[-1]
        
        # Near lower band - potential buy
        if position < 0.2:
            strength = min((0.2 - position) / 0.2, 1.0)
            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=current_price,
                stop_loss=current_lower,
                take_profit=current_middle,
                strength=strength,
                metadata={"strategy": "BB", "position": position}
            )
        
        # Near upper band - potential sell
        if position > 0.8:
            strength = min((position - 0.8) / 0.2, 1.0)
            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                price=current_price,
                stop_loss=current_middle,
                take_profit=current_upper,
                strength=strength,
                metadata={"strategy": "BB", "position": position}
            )
        
        return Signal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            price=current_price,
            metadata={"strategy": "BB", "position": position}
        )


# Registry of built-in strategies
BUILTIN_STRATEGIES: dict[str, type[Strategy]] = {
    "ma_cross": MAStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "bollinger": BollingerStrategy,
}
