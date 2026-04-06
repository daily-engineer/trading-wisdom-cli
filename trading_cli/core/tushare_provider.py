"""Tushare data provider for A-shares market data."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import requests

from trading_cli.core.config import TushareConfig
from trading_cli.core.data_source import (
    DataFetchRequest,
    DataFetchResult,
    DataFrequency,
    Market,
)


class TushareProvider:
    """Tushare Pro API data provider."""

    def __init__(self, config: TushareConfig) -> None:
        self._config = config

    @property
    def name(self) -> str:
        return "tushare"

    @property
    def supported_markets(self) -> list[Market]:
        return [Market.CN]

    def fetch_stock_daily(self, request: DataFetchRequest) -> DataFetchResult:
        """Fetch daily stock data from Tushare Pro API."""
        if not self._config.token:
            raise RuntimeError(
                "Tushare Token 未配置。"
                "请运行: trading-cli config set data.tushare.token <YOUR_TOKEN>"
            )
        start = request.start_date or (date.today() - timedelta(days=365))
        end = request.end_date or date.today()

        params = {
            "api_name": "daily",
            "token": self._config.token,
            "params": {
                "ts_code": self._normalize_symbol(request.symbol),
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
            "fields": "ts_code,trade_date,open,high,low,close,vol,amount",
        }

        resp = requests.post(
            self._config.api_url,
            json=params,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("code") != 0:
            msg = result.get("msg", "unknown error")
            if not self._config.token or "token" in msg.lower() or "Token" in msg:
                raise RuntimeError(
                    "Tushare Token 未配置或无效。"
                    "请运行: trading-cli config set data.tushare.token <YOUR_TOKEN>"
                )
            raise RuntimeError(f"Tushare API 错误: {msg}")

        fields = result["data"]["fields"]
        items = result["data"]["items"] or []
        df = pd.DataFrame(items, columns=fields)

        if not df.empty:
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
        """Check if Tushare API is accessible."""
        if not self._config.token:
            return False
        try:
            params = {
                "api_name": "daily",
                "token": self._config.token,
                "params": {
                    "ts_code": "000001.SZ",
                    "start_date": date.today().strftime("%Y%m%d"),
                    "end_date": date.today().strftime("%Y%m%d"),
                },
            }
            resp = requests.post(self._config.api_url, json=params, timeout=10)
            return resp.status_code == 200 and resp.json().get("code") == 0
        except (requests.RequestException, KeyError):
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
