"""Interactive Brokers data provider.

Provides a DataProvider implementation that can operate in two modes:
- **live**: connects to IB TWS/Gateway via ib_insync (requires ib_insync + running TWS)
- **simulated**: generates realistic demo data for development and testing

The simulated mode allows full CLI testing without an IB account.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from trading_cli.core.data_source import (
    DataFetchRequest, DataFetchResult, DataFrequency, DataProvider, Market,
)
from trading_cli.core.market import detect_market, normalize_symbol


class IBProvider:
    """Interactive Brokers data provider with live and simulated modes."""

    def __init__(self, host: str = "127.0.0.1", port: int = 7497,
                 client_id: int = 1, simulated: bool = True):
        self._host = host
        self._port = port
        self._client_id = client_id
        self._simulated = simulated
        self._ib = None  # ib_insync.IB instance (lazy)

    @property
    def name(self) -> str:
        return "ib"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.US, Market.HK]

    def fetch_stock_daily(self, request: DataFetchRequest) -> DataFetchResult:
        """Fetch daily stock data."""
        if self._simulated:
            return self._simulated_fetch(request)
        return self._live_fetch(request)

    def check_connection(self) -> bool:
        if self._simulated:
            return True
        try:
            ib = self._get_ib()
            return ib.isConnected()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Simulated mode — generates realistic synthetic data
    # ------------------------------------------------------------------

    def _simulated_fetch(self, request: DataFetchRequest) -> DataFetchResult:
        symbol = request.symbol.upper()
        mkt_code = detect_market(symbol)
        market = Market.US if mkt_code == "US" else Market.HK

        start = request.start_date or (date.today() - timedelta(days=365))
        end = request.end_date or date.today()

        # Deterministic seed from symbol
        seed = sum(ord(c) for c in symbol)
        rng = np.random.RandomState(seed)

        # Generate trading days (weekdays only)
        all_days = pd.bdate_range(start, end)
        n = len(all_days)
        if n == 0:
            return DataFetchResult(
                symbol=symbol, provider=self.name, market=market,
                frequency=DataFrequency.DAILY, row_count=0,
                columns=[], data=pd.DataFrame(),
            )

        # Price simulation: geometric Brownian motion
        base_prices = {
            "AAPL": 185.0, "MSFT": 420.0, "GOOGL": 175.0, "AMZN": 185.0,
            "TSLA": 250.0, "SPY": 530.0, "QQQ": 450.0, "META": 500.0,
            "NVDA": 900.0, "0700.HK": 380.0, "9988.HK": 85.0,
            "1810.HK": 17.0, "2318.HK": 45.0, "0005.HK": 60.0,
        }
        clean_sym = symbol.split(".")[0] if "." in symbol else symbol
        base = base_prices.get(symbol, base_prices.get(clean_sym, 100.0))

        daily_returns = rng.normal(0.0003, 0.018, n)
        prices = base * np.cumprod(1 + daily_returns)

        high_noise = np.abs(rng.normal(0, 0.008, n))
        low_noise = np.abs(rng.normal(0, 0.008, n))
        open_noise = rng.normal(0, 0.003, n)

        df = pd.DataFrame({
            "trade_date": all_days,
            "open": np.round(prices * (1 + open_noise), 2),
            "high": np.round(prices * (1 + high_noise), 2),
            "low": np.round(prices * (1 - low_noise), 2),
            "close": np.round(prices, 2),
            "vol": (rng.lognormal(15, 0.8, n)).astype(int),
            "amount": np.round(prices * rng.lognormal(15, 0.8, n), 0),
        })

        # Ensure OHLC consistency
        df["high"] = df[["open", "high", "close"]].max(axis=1)
        df["low"] = df[["open", "low", "close"]].min(axis=1)

        return DataFetchResult(
            symbol=symbol, provider=self.name, market=market,
            frequency=request.frequency, row_count=len(df),
            columns=list(df.columns), data=df,
            fetched_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    # Live mode — real IB TWS/Gateway connection
    # ------------------------------------------------------------------

    def _get_ib(self):
        """Lazy-connect to IB TWS/Gateway."""
        if self._ib is None:
            try:
                from ib_insync import IB
                self._ib = IB()
                self._ib.connect(self._host, self._port, clientId=self._client_id)
            except ImportError:
                raise RuntimeError(
                    "ib_insync is required for live IB mode. "
                    "Install with: pip install ib_insync"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to connect to IB TWS/Gateway: {e}")
        return self._ib

    def _live_fetch(self, request: DataFetchRequest) -> DataFetchResult:
        """Fetch real data from IB TWS."""
        try:
            from ib_insync import Stock, util
        except ImportError:
            raise RuntimeError("ib_insync required for live mode")

        ib = self._get_ib()
        symbol = request.symbol.upper()
        mkt = detect_market(symbol)

        # Build contract
        if mkt == "HK":
            clean = symbol.replace(".HK", "")
            contract = Stock(clean, "SEHK", "HKD")
        else:
            clean = symbol.split(".")[0]
            contract = Stock(clean, "SMART", "USD")

        ib.qualifyContracts(contract)

        end = request.end_date or date.today()
        start = request.start_date or (end - timedelta(days=365))
        duration = f"{(end - start).days} D"

        bars = ib.reqHistoricalData(
            contract, endDateTime=end.strftime("%Y%m%d 23:59:59"),
            durationStr=duration, barSizeSetting="1 day",
            whatToShow="TRADES", useRTH=True,
        )

        df = util.df(bars) if bars else pd.DataFrame()
        if not df.empty:
            df = df.rename(columns={"date": "trade_date", "volume": "vol"})
            if "trade_date" in df.columns:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
            df["amount"] = df.get("close", 0) * df.get("vol", 0)

        market = Market.HK if mkt == "HK" else Market.US
        return DataFetchResult(
            symbol=symbol, provider=self.name, market=market,
            frequency=DataFrequency.DAILY, row_count=len(df),
            columns=list(df.columns), data=df,
            fetched_at=datetime.now(),
        )

    def disconnect(self) -> None:
        """Disconnect from IB."""
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            self._ib = None
