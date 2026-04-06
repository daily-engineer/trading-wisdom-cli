"""Technical indicators for market analysis."""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional


class TechnicalIndicators:
    """Calculate common technical indicators for trading analysis."""

    @staticmethod
    def sma(data: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average."""
        return data.rolling(window=period).mean()

    @staticmethod
    def ema(data: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average."""
        return data.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index."""
        delta = data.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def macd(
        data: pd.Series,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """MACD (Moving Average Convergence Divergence).
        
        Returns:
            macd_line, signal_line, histogram
        """
        ema_fast = data.ewm(span=fast_period, adjust=False).mean()
        ema_slow = data.ewm(span=slow_period, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(
        data: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Bollinger Bands.
        
        Returns:
            upper_band, middle_band, lower_band
        """
        middle = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return upper, middle, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Average True Range."""
        high_low = high - low
        high_close = (high - close.shift(1)).abs()
        low_close = (low - close.shift(1)).abs()
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        
        return atr

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Average Directional Index."""
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        tr = TechnicalIndicators._true_range(high, low, close)
        
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr.rolling(window=period).mean())
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr.rolling(window=period).mean())
        
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
        adx = dx.rolling(window=period).mean()
        
        return adx

    @staticmethod
    def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        """Calculate True Range."""
        high_low = high - low
        high_close = (high - close.shift(1)).abs()
        low_close = (low - close.shift(1)).abs()
        return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

    @staticmethod
    def stochastic(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int = 14,
        d_period: int = 3
    ) -> tuple[pd.Series, pd.Series]:
        """Stochastic Oscillator.
        
        Returns:
            %K line, %D line
        """
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(window=d_period).mean()
        
        return k, d

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """On-Balance Volume."""
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        return obv

    @staticmethod
    def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
        """Commodity Channel Index."""
        tp = (high + low + close) / 3
        sma_tp = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (tp - sma_tp) / (0.015 * mad)
        return cci

    @staticmethod
    def all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all available indicators and add as columns.
        
        Args:
            df: DataFrame with 'high', 'low', 'close', 'vol' columns
        Returns:
            DataFrame with additional indicator columns
        """
        result = df.copy()
        
        # Moving Averages
        for period in [5, 10, 20, 60]:
            result[f'sma_{period}'] = TechnicalIndicators.sma(df['close'], period)
            result[f'ema_{period}'] = TechnicalIndicators.ema(df['close'], period)
        
        # RSI
        result['rsi_14'] = TechnicalIndicators.rsi(df['close'], 14)
        
        # MACD
        macd, signal, hist = TechnicalIndicators.macd(df['close'])
        result['macd'] = macd
        result['macd_signal'] = signal
        result['macd_hist'] = hist
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(df['close'])
        result['bb_upper'] = bb_upper
        result['bb_middle'] = bb_middle
        result['bb_lower'] = bb_lower
        result['bb_width'] = (bb_upper - bb_lower) / bb_middle
        
        # ATR (requires high, low, close)
        if all(col in df.columns for col in ['high', 'low']):
            result['atr_14'] = TechnicalIndicators.atr(df['high'], df['low'], df['close'], 14)
        
        # Stochastic
        if all(col in df.columns for col in ['high', 'low']):
            k, d = TechnicalIndicators.stochastic(df['high'], df['low'], df['close'])
            result['stoch_k'] = k
            result['stoch_d'] = d
        
        # OBV
        if 'vol' in df.columns:
            result['obv'] = TechnicalIndicators.obv(df['close'], df['vol'])
        
        # CCI
        if all(col in df.columns for col in ['high', 'low']):
            result['cci_20'] = TechnicalIndicators.cci(df['high'], df['low'], df['close'], 20)
        
        return result
