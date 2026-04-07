"""Tushare data provider for A-shares market data (via twostock SDK)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

import twostock as ts

from trading_cli.core.config import TushareConfig
from trading_cli.core.data_source import (
    DataFetchRequest,
    DataFetchResult,
    DataFrequency,
    Market,
)


class TushareProvider:
    """Tushare Pro API data provider (backed by twostock SDK)."""

    def __init__(self, config: TushareConfig) -> None:
        self._config = config
        if config.token:
            ts.set_token(config.token)

    @property
    def name(self) -> str:
        return "tushare"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.CN]

    def fetch_stock_daily(self, request: DataFetchRequest) -> DataFetchResult:
        """Fetch daily stock data from Tushare Pro API via twostock SDK."""
        if not self._config.token:
            raise RuntimeError(
                "Tushare Token 未配置。"
                "请运行: trading-cli config set data.tushare.token <YOUR_TOKEN>"
            )
        start = request.start_date or (date.today() - timedelta(days=365))
        end = request.end_date or date.today()

        pro = ts.pro_api()
        df = pro.daily(
            ts_code=self._normalize_symbol(request.symbol),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )

        if df is None or df.empty:
            df = pd.DataFrame(
                columns=["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"]
            )
        else:
            if "trade_date" in df.columns:
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df = df.sort_values("trade_date").reset_index(drop=True)

        return DataFetchResult(
            symbol=request.symbol,
            provider=self.name,
            market=Market.CN,
            frequency=request.frequency,
            row_count=len(df),
            columns=list(df.columns),
            data=df,
            fetched_at=datetime.now(),
        )

    def check_connection(self) -> bool:
        """Check if Tushare API is accessible via twostock SDK."""
        if not self._config.token:
            return False
        try:
            pro = ts.pro_api()
            df = pro.daily(
                ts_code="000001.SZ",
                start_date=date.today().strftime("%Y%m%d"),
                end_date=date.today().strftime("%Y%m%d"),
            )
            # If no error raised, connection is OK
            return True
        except Exception:
            return False

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalize symbol to Tushare format (e.g., 000001 -> 000001.SZ)."""
        if "." in symbol:
            return symbol.upper()
        # Guess exchange by code prefix
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        return f"{symbol}.SZ"
