"""Tests for RealTrader and TradeLogger — all ib_insync calls are mocked."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock
from pathlib import Path

import pytest

from trading_cli.core.order import Order, OrderSide, OrderStatus, OrderType
from trading_cli.core.trade_logger import TradeLogger


class TestTradeLogger:
    def test_log_writes_correct_fields(self, tmp_path):
        log_file = tmp_path / "trade_log.jsonl"
        logger = TradeLogger(log_path=log_file)

        order = Order(
            id="LIVE-00001",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
            status=OrderStatus.FILLED,
            filled_price=185.10,
            filled_quantity=100,
        )
        logger.log(order, mode="live", account_id="U1234567")

        entries = [json.loads(line) for line in log_file.read_text().splitlines()]
        assert len(entries) == 1
        e = entries[0]
        assert e["symbol"] == "AAPL"
        assert e["side"] == "BUY"
        assert e["quantity"] == 100
        assert e["filled_price"] == pytest.approx(185.10)
        assert e["status"] == "FILLED"
        assert e["mode"] == "live"
        assert e["order_id"] == "LIVE-00001"
        assert e["account_id_suffix"] == "4567"

    def test_log_no_token_leakage(self, tmp_path):
        log_file = tmp_path / "trade_log.jsonl"
        logger = TradeLogger(log_path=log_file)

        order = Order(
            id="LIVE-00002",
            symbol="MSFT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=50,
            status=OrderStatus.FILLED,
            filled_price=420.0,
            filled_quantity=50,
        )
        logger.log(order, mode="live", account_id="token_secret_password")

        raw = log_file.read_text()
        assert "token_secret_password" not in raw
        assert "secret" not in raw
        # account_id_suffix should only be last 4 chars
        entry = json.loads(raw.strip())
        assert entry["account_id_suffix"] == "word"  # last 4 of "token_secret_password"
