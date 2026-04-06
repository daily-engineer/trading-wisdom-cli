"""Tests for technical indicators."""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from trading_cli.core.indicators import TechnicalIndicators


@pytest.fixture
def sample_data():
    """Generate sample OHLCV data for testing."""
    dates = pd.date_range(start=date.today() - timedelta(days=100), end=date.today(), freq='D')
    n = len(dates)
    
    # Generate realistic price data with trend
    np.random.seed(42)
    trend = np.linspace(0, 10, n)
    noise = np.random.randn(n) * 2
    
    close = 100 + trend + noise
    high = close + np.abs(np.random.randn(n)) * 1.5
    low = close - np.abs(np.random.randn(n)) * 1.5
    open_price = close + np.random.randn(n) * 0.5
    volume = np.random.randint(1000000, 10000000, n)
    
    df = pd.DataFrame({
        'trade_date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'vol': volume
    })
    
    return df


class TestMovingAverages:
    """Test moving average calculations."""
    
    def test_sma(self, sample_data):
        """Test SMA calculation."""
        sma_20 = TechnicalIndicators.sma(sample_data['close'], 20)
        assert not sma_20.iloc[-1] != sample_data['close'].iloc[-20:].mean()
    
    def test_ema(self, sample_data):
        """Test EMA calculation."""
        ema_20 = TechnicalIndicators.ema(sample_data['close'], 20)
        assert ema_20.iloc[-1] > 0
        assert not pd.isna(ema_20.iloc[-1])


class TestMomentumIndicators:
    """Test momentum-based indicators."""
    
    def test_rsi(self, sample_data):
        """Test RSI calculation."""
        rsi = TechnicalIndicators.rsi(sample_data['close'], 14)
        valid_rsi = rsi.dropna()
        assert len(valid_rsi) > 0
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()
    
    def test_macd(self, sample_data):
        """Test MACD calculation."""
        macd, signal, hist = TechnicalIndicators.macd(sample_data['close'])
        assert len(macd) == len(sample_data)
        assert len(signal) == len(sample_data)
        assert len(hist) == len(sample_data)


class TestVolatilityIndicators:
    """Test volatility-based indicators."""
    
    def test_bollinger_bands(self, sample_data):
        """Test Bollinger Bands calculation."""
        upper, middle, lower = TechnicalIndicators.bollinger_bands(sample_data['close'])
        
        valid_upper = upper.dropna()
        valid_middle = middle.dropna()
        valid_lower = lower.dropna()
        
        assert len(valid_upper) > 0
        assert len(valid_middle) > 0
        assert len(valid_lower) > 0
        assert (valid_upper >= valid_middle).all()
        assert (valid_middle >= valid_lower).all()
    
    def test_atr(self, sample_data):
        """Test ATR calculation."""
        atr = TechnicalIndicators.atr(
            sample_data['high'],
            sample_data['low'],
            sample_data['close']
        )
        valid_atr = atr.dropna()
        assert len(valid_atr) > 0
        assert (valid_atr > 0).all()


class TestOscillators:
    """Test oscillator indicators."""
    
    def test_stochastic(self, sample_data):
        """Test Stochastic oscillator."""
        k, d = TechnicalIndicators.stochastic(
            sample_data['high'],
            sample_data['low'],
            sample_data['close']
        )
        assert len(k) == len(sample_data)
        assert len(d) == len(sample_data)
    
    def test_cci(self, sample_data):
        """Test CCI calculation."""
        cci = TechnicalIndicators.cci(
            sample_data['high'],
            sample_data['low'],
            sample_data['close']
        )
        assert cci.notna().sum() > 0


class TestVolumeIndicators:
    """Test volume-based indicators."""
    
    def test_obv(self, sample_data):
        """Test OBV calculation."""
        obv = TechnicalIndicators.obv(sample_data['close'], sample_data['vol'])
        assert len(obv) == len(sample_data)
        # OBV is cumulative, so just verify it has reasonable values
        assert abs(obv.iloc[-1]) > 0 or obv.notna().all()


class TestAllIndicators:
    """Test the combined all_indicators method."""
    
    def test_all_indicators(self, sample_data):
        """Test that all_indicators returns expected columns."""
        result = TechnicalIndicators.all_indicators(sample_data)
        
        # Check for expected columns
        expected_cols = [
            'sma_5', 'sma_10', 'sma_20', 'sma_60',
            'ema_5', 'ema_10', 'ema_20', 'ema_60',
            'rsi_14',
            'macd', 'macd_signal', 'macd_hist',
            'bb_upper', 'bb_middle', 'bb_lower', 'bb_width',
            'atr_14',
            'stoch_k', 'stoch_d',
            'obv',
            'cci_20'
        ]
        
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"
        
        # Check row count preserved
        assert len(result) == len(sample_data)
