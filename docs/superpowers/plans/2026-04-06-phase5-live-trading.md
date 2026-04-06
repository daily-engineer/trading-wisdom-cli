# Phase 5 Live Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add IBKR live trading to the CLI via a `BaseTrader` abstraction, safety confirmation layer, JSON Lines audit log, and emergency stop command.

**Architecture:** Extract `BaseTrader` ABC that both `PaperTrader` and `RealTrader` implement. `RealTrader` wraps `ib_insync` with synchronous blocking calls. `trade_cmd.py` routes to the right trader based on `--live` flag. `TradeLogger` writes every order to `~/.trading-cli/trade_log.jsonl`.

**Tech Stack:** Python 3.10+, click, ib_insync (optional, lazy import), pydantic, pytest + unittest.mock

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `trading_cli/core/base_trader.py` | `BaseTrader` ABC — common interface for paper and live |
| Create | `trading_cli/core/trade_logger.py` | `TradeLogger` — JSON Lines audit log |
| Create | `trading_cli/core/live_trader.py` | `RealTrader` — ib_insync live execution |
| Create | `tests/test_live_trader.py` | Unit tests (12), all mock ib_insync |
| Modify | `trading_cli/core/paper_trader.py` | Inherit `BaseTrader`, add `emergency_stop` |
| Modify | `trading_cli/commands/trade_cmd.py` | `--live`/`--yes` flags, emergency stop command, log wiring |

---

## Task 1: BaseTrader ABC

**Files:**
- Create: `trading_cli/core/base_trader.py`
- Modify: `trading_cli/core/paper_trader.py` (inherit + add `emergency_stop`)
- Test: `tests/test_trade.py` (add 2 assertions to existing test class — no new file)

- [ ] **Step 1: Write failing test for BaseTrader inheritance**

Add to `tests/test_trade.py` inside `class TestPaperTrader:`:

```python
def test_paper_trader_is_base_trader(self):
    from trading_cli.core.base_trader import BaseTrader
    trader = PaperTrader()
    assert isinstance(trader, BaseTrader)

def test_emergency_stop_cancels_then_closes(self):
    trader = PaperTrader(initial_capital=100000)
    # Place a limit order (stays pending)
    trader.place_order("TEST", OrderSide.BUY, 100,
                       order_type=OrderType.LIMIT, price=5.0,
                       current_price=10.0)
    # Buy a position
    trader.place_order("TEST2", OrderSide.BUY, 50, current_price=20.0)

    orders = trader.emergency_stop({"TEST2": 20.0})

    # Pending order should be cancelled
    open_orders = trader.account.get_open_orders()
    assert len(open_orders) == 0
    # Position should be closed
    assert trader.account.position_count == 0
    # One sell order returned
    assert len(orders) == 1
    assert orders[0].side == OrderSide.SELL
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/macbot/workspace/daily-engineer/trading-wisdom-cli
python -m pytest tests/test_trade.py::TestPaperTrader::test_paper_trader_is_base_trader -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'trading_cli.core.base_trader'`

- [ ] **Step 3: Create `base_trader.py`**

```python
# trading_cli/core/base_trader.py
"""Abstract base class for all trader implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from trading_cli.core.order import Order, OrderSide, OrderType
from trading_cli.core.risk import RiskCheckResult


class BaseTrader(ABC):
    """Common interface for paper and live trading engines."""

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> Order: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def close_position(self, symbol: str, current_price: float) -> Optional[Order]: ...

    @abstractmethod
    def emergency_stop(self, prices: dict[str, float]) -> list[Order]: ...

    @abstractmethod
    def check_risk(self) -> RiskCheckResult: ...
```

- [ ] **Step 4: Update `paper_trader.py` to inherit `BaseTrader` and add `emergency_stop`**

Change line 1 imports and class declaration:

```python
# At top of file, add import:
from trading_cli.core.base_trader import BaseTrader

# Change class line from:
class PaperTrader:
# To:
class PaperTrader(BaseTrader):
```

Add `emergency_stop` method at the end of `PaperTrader` (after `_execute_order`):

```python
def emergency_stop(self, prices: dict[str, float]) -> list[Order]:
    """Cancel all open orders then market-sell all positions."""
    orders: list[Order] = []

    # Step 1: cancel all open orders
    for order in list(self.account.get_open_orders()):
        self.cancel_order(order.id)

    # Step 2: close all positions
    for symbol in list(self.account.positions.keys()):
        pos = self.account.positions.get(symbol)
        if pos is None:
            continue
        price = prices.get(symbol, pos.current_price)
        if price > 0:
            result = self.close_position(symbol, price)
            if result:
                orders.append(result)

    return orders
```

- [ ] **Step 5: Run all trade tests**

```bash
python -m pytest tests/test_trade.py -v
```

Expected: All tests pass (including the 2 new ones). Output ends with `X passed`.

- [ ] **Step 6: Run full suite to check no regressions**

```bash
python -m pytest tests/ --tb=short -q
```

Expected: 163 passed (161 existing + 2 new).

- [ ] **Step 7: Commit**

```bash
git add trading_cli/core/base_trader.py trading_cli/core/paper_trader.py tests/test_trade.py
git commit -m "feat: add BaseTrader ABC and update PaperTrader to inherit it"
```

---

## Task 2: TradeLogger

**Files:**
- Create: `trading_cli/core/trade_logger.py`
- Test: `tests/test_live_trader.py` (create new file, first 2 tests only)

- [ ] **Step 1: Create test file with TradeLogger tests**

Create `tests/test_live_trader.py`:

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_live_trader.py::TestTradeLogger -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'trading_cli.core.trade_logger'`

- [ ] **Step 3: Create `trade_logger.py`**

```python
# trading_cli/core/trade_logger.py
"""JSON Lines audit log for all trade orders."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from trading_cli.core.order import Order

DEFAULT_LOG_PATH = Path.home() / ".trading-cli" / "trade_log.jsonl"


class TradeLogger:
    """Appends one JSON line per order to an audit log file."""

    def __init__(self, log_path: Optional[Path] = None):
        self._path = log_path or DEFAULT_LOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        order: Order,
        mode: str = "paper",
        account_id: str = "",
    ) -> None:
        """Append one log entry. account_id is truncated to last 4 chars."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "order_type": order.order_type.value,
            "price": order.price,
            "filled_price": order.filled_price if order.filled_price else None,
            "status": order.status.value,
            "order_id": order.id,
            "account_id_suffix": account_id[-4:] if account_id else "",
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 4: Run TradeLogger tests**

```bash
python -m pytest tests/test_live_trader.py::TestTradeLogger -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add trading_cli/core/trade_logger.py tests/test_live_trader.py
git commit -m "feat: add TradeLogger (JSON Lines audit log)"
```

---

## Task 3: RealTrader

**Files:**
- Create: `trading_cli/core/live_trader.py`
- Modify: `tests/test_live_trader.py` (add `TestRealTrader` class, 10 tests)

- [ ] **Step 1: Add RealTrader tests to `test_live_trader.py`**

Append to `tests/test_live_trader.py` (after the `TestTradeLogger` class):

```python
from trading_cli.core.live_trader import RealTrader


def _make_mock_ib_module():
    """Return (mock_module, mock_ib_instance) with sensible defaults."""
    ib_instance = MagicMock()
    ib_instance.isConnected.return_value = True
    ib_instance.positions.return_value = []
    mock_mod = MagicMock()
    mock_mod.IB.return_value = ib_instance
    return mock_mod, ib_instance


def _filled_trade(price: float = 100.0, qty: float = 100.0) -> MagicMock:
    t = MagicMock()
    t.orderStatus.status = "Filled"
    t.orderStatus.avgFillPrice = price
    t.orderStatus.filled = qty
    return t


def _pending_trade() -> MagicMock:
    t = MagicMock()
    t.orderStatus.status = "Submitted"
    t.orderStatus.avgFillPrice = 0.0
    t.orderStatus.filled = 0.0
    return t


def _inactive_trade() -> MagicMock:
    t = MagicMock()
    t.orderStatus.status = "Inactive"
    t.orderStatus.avgFillPrice = 0.0
    t.orderStatus.filled = 0.0
    return t


@pytest.fixture
def mock_ib(monkeypatch):
    """Inject a mock ib_insync module and return (mock_module, ib_instance)."""
    mock_mod, ib_instance = _make_mock_ib_module()
    monkeypatch.setitem(sys.modules, "ib_insync", mock_mod)
    return mock_mod, ib_instance


class TestRealTrader:
    def test_place_order_buy_filled(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _filled_trade(185.10, 100.0)

        trader = RealTrader()
        order = trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)

        assert order.status == OrderStatus.FILLED
        assert order.filled_price == pytest.approx(185.10)
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY

    def test_place_order_sell_filled(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _filled_trade(185.0, 100.0)

        trader = RealTrader()
        order = trader.place_order("AAPL", OrderSide.SELL, 100, current_price=185.0)

        assert order.status == OrderStatus.FILLED
        assert order.side == OrderSide.SELL

    def test_place_order_rejected(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _inactive_trade()

        trader = RealTrader()
        order = trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)

        assert order.status == OrderStatus.REJECTED

    def test_cancel_order_success(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.placeOrder.return_value = _pending_trade()

        trader = RealTrader()
        order = trader.place_order("AAPL", OrderSide.BUY, 100,
                                   order_type=OrderType.LIMIT, price=184.0)
        result = trader.cancel_order(order.id)

        assert result is True
        ib.cancelOrder.assert_called_once()

    def test_cancel_order_not_found(self, mock_ib):
        _, _ = mock_ib
        trader = RealTrader()
        assert trader.cancel_order("NONEXISTENT") is False

    def test_close_position_with_holding(self, mock_ib):
        mock_mod, ib = mock_ib
        pos_mock = MagicMock()
        pos_mock.contract.symbol = "AAPL"
        pos_mock.position = 100.0
        ib.positions.return_value = [pos_mock]
        ib.placeOrder.return_value = _filled_trade(185.0, 100.0)

        trader = RealTrader()
        order = trader.close_position("AAPL", 185.0)

        assert order is not None
        assert order.side == OrderSide.SELL
        assert order.quantity == 100

    def test_close_position_no_holding(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.positions.return_value = []

        trader = RealTrader()
        order = trader.close_position("AAPL", 185.0)

        assert order is None

    def test_emergency_stop_cancels_then_closes(self, mock_ib):
        mock_mod, ib = mock_ib
        pos_mock = MagicMock()
        pos_mock.contract.symbol = "AAPL"
        pos_mock.position = 100.0
        ib.positions.return_value = [pos_mock]
        ib.placeOrder.return_value = _filled_trade(185.0, 100.0)

        trader = RealTrader()
        orders = trader.emergency_stop({"AAPL": 185.0})

        ib.reqGlobalCancel.assert_called_once()
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL

    def test_emergency_stop_no_positions(self, mock_ib):
        mock_mod, ib = mock_ib
        ib.positions.return_value = []

        trader = RealTrader()
        orders = trader.emergency_stop({})

        ib.reqGlobalCancel.assert_called_once()
        assert orders == []

    def test_ib_not_installed_raises(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "ib_insync", None)

        trader = RealTrader()
        with pytest.raises(RuntimeError, match="ib_insync is required"):
            trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)

    def test_connection_failure_raises(self, monkeypatch):
        mock_mod = MagicMock()
        mock_mod.IB.return_value.connect.side_effect = OSError("Connection refused")
        monkeypatch.setitem(sys.modules, "ib_insync", mock_mod)

        trader = RealTrader()
        with pytest.raises(RuntimeError, match="Failed to connect"):
            trader.place_order("AAPL", OrderSide.BUY, 100, current_price=185.0)
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_live_trader.py::TestRealTrader -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'trading_cli.core.live_trader'`

- [ ] **Step 3: Create `live_trader.py`**

```python
# trading_cli/core/live_trader.py
"""Live trading engine backed by Interactive Brokers via ib_insync."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from trading_cli.core.base_trader import BaseTrader
from trading_cli.core.market import detect_market
from trading_cli.core.order import Order, OrderSide, OrderStatus, OrderType
from trading_cli.core.risk import RiskCheckResult, RiskEngine
from trading_cli.core.trade_logger import TradeLogger


class RealTrader(BaseTrader):
    """Live IBKR trading engine.

    Connects to IB TWS/Gateway via ib_insync (lazy connection on first use).
    Credentials are read from environment variables: IB_HOST, IB_PORT, IB_CLIENT_ID.
    """

    def __init__(
        self,
        host: str = "",
        port: int = 0,
        client_id: int = 0,
        fill_timeout: float = 10.0,
        logger: Optional[TradeLogger] = None,
        account_id: str = "",
    ):
        self._host = host or os.environ.get("IB_HOST", "127.0.0.1")
        self._port = port or int(os.environ.get("IB_PORT", "7497"))
        self._client_id = client_id or int(os.environ.get("IB_CLIENT_ID", "1"))
        self._fill_timeout = fill_timeout
        self._ib: Optional[Any] = None
        self._trades: dict[str, Any] = {}  # order_id -> ib_insync.Trade
        self._order_counter = 0
        self.logger = logger or TradeLogger()
        self._account_id = account_id
        self._risk_engine = RiskEngine()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _get_ib(self) -> Any:
        """Lazy-connect to IB TWS/Gateway."""
        if self._ib is None:
            try:
                from ib_insync import IB

                self._ib = IB()
                self._ib.connect(self._host, self._port, clientId=self._client_id)
            except ImportError:
                raise RuntimeError(
                    "ib_insync is required for live trading. "
                    "Install with: pip install ib_insync"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to connect to IB TWS/Gateway: {e}")
        return self._ib

    def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            self._ib = None

    # ------------------------------------------------------------------
    # Contract helpers
    # ------------------------------------------------------------------

    def _build_contract(self, symbol: str) -> Any:
        from ib_insync import Stock

        mkt = detect_market(symbol.upper())
        if mkt == "HK":
            return Stock(symbol.upper().replace(".HK", ""), "SEHK", "HKD")
        return Stock(symbol.upper().split(".")[0], "SMART", "USD")

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"LIVE-{self._order_counter:05d}"

    def _map_status(self, ib_status: str) -> OrderStatus:
        return {
            "Filled": OrderStatus.FILLED,
            "Cancelled": OrderStatus.CANCELLED,
            "Inactive": OrderStatus.REJECTED,
        }.get(ib_status, OrderStatus.PENDING)

    def _get_position_qty(self, symbol: str) -> int:
        ib = self._get_ib()
        clean = symbol.upper().replace(".HK", "").split(".")[0]
        for pos in ib.positions():
            if pos.contract.symbol == clean:
                return int(pos.position)
        return 0

    # ------------------------------------------------------------------
    # BaseTrader interface
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> Order:
        from ib_insync import LimitOrder, MarketOrder

        ib = self._get_ib()
        contract = self._build_contract(symbol)
        ib.qualifyContracts(contract)

        ib_action = "BUY" if side == OrderSide.BUY else "SELL"
        if order_type == OrderType.LIMIT and price:
            ib_order = LimitOrder(ib_action, quantity, price)
        else:
            ib_order = MarketOrder(ib_action, quantity)

        order_id = self._next_order_id()
        trade = ib.placeOrder(contract, ib_order)
        self._trades[order_id] = trade

        ib.sleep(self._fill_timeout)

        status = self._map_status(trade.orderStatus.status)
        filled_price = float(trade.orderStatus.avgFillPrice or 0.0)
        filled_qty = int(trade.orderStatus.filled or 0)

        order = Order(
            id=order_id,
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            status=status,
            filled_quantity=filled_qty,
            filled_price=filled_price,
            filled_at=datetime.now() if status == OrderStatus.FILLED else None,
        )

        self.logger.log(order, mode="live", account_id=self._account_id)
        return order

    def cancel_order(self, order_id: str) -> bool:
        trade = self._trades.get(order_id)
        if not trade:
            return False
        try:
            ib = self._get_ib()
            ib.cancelOrder(trade.order)
            ib.sleep(1.0)
            return True
        except Exception:
            return False

    def close_position(self, symbol: str, current_price: float) -> Optional[Order]:
        qty = self._get_position_qty(symbol)
        if qty <= 0:
            return None
        return self.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=qty,
            current_price=current_price,
        )

    def emergency_stop(self, prices: dict[str, float]) -> list[Order]:
        """Cancel all open orders then market-sell all IB positions."""
        ib = self._get_ib()
        orders: list[Order] = []

        # Step 1: cancel everything
        ib.reqGlobalCancel()
        ib.sleep(1.0)

        # Step 2: close all positions
        for pos in ib.positions():
            qty = int(pos.position)
            if qty <= 0:
                continue
            symbol = pos.contract.symbol
            price = prices.get(symbol, 0.0)
            order = self.place_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=qty,
                current_price=price,
            )
            orders.append(order)

        return orders

    def check_risk(self) -> RiskCheckResult:
        try:
            ib = self._get_ib()
            if not ib.isConnected():
                return RiskCheckResult(passed=False, violations=["IB not connected"])
            return RiskCheckResult(passed=True, violations=[])
        except Exception as e:
            return RiskCheckResult(passed=False, violations=[str(e)])
```

- [ ] **Step 4: Run RealTrader tests**

```bash
python -m pytest tests/test_live_trader.py -v
```

Expected: `12 passed`

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ --tb=short -q
```

Expected: 175 passed (163 + 12 new).

- [ ] **Step 6: Commit**

```bash
git add trading_cli/core/live_trader.py tests/test_live_trader.py
git commit -m "feat: add RealTrader (ib_insync live execution) with 12 unit tests"
```

---

## Task 4: trade_cmd.py — `--live`/`--yes` flags + emergency stop

**Files:**
- Modify: `trading_cli/commands/trade_cmd.py`
- Test: `tests/test_cli.py` (add CLI-runner tests for emergency stop and live flag)

- [ ] **Step 1: Write failing CLI tests**

Read `tests/test_cli.py` first to understand the existing fixture pattern, then add:

```python
def test_emergency_stop_paper(cli_runner):
    """Emergency stop in paper mode should return an empty-positions message."""
    result = cli_runner.invoke(cli, ["trade", "emergency", "stop"])
    assert result.exit_code == 0
    assert "No open positions" in result.output or "emergency" in result.output.lower()

def test_order_buy_live_requires_confirm(cli_runner):
    """--live flag without --yes should prompt for confirmation."""
    result = cli_runner.invoke(
        cli, ["trade", "order", "buy", "AAPL", "--qty", "1", "--live"],
        input="n\n"
    )
    assert result.exit_code == 0
    assert "LIVE ORDER" in result.output
    assert "Cancelled" in result.output or "cancelled" in result.output.lower()
```

Check where `cli_runner` fixture is defined in `tests/test_cli.py`:

```bash
grep -n "cli_runner\|def test_" tests/test_cli.py | head -20
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_cli.py -k "emergency_stop or live_requires" -v
```

Expected: `FAILED` — no `emergency` subcommand exists yet.

- [ ] **Step 3: Rewrite `trading_cli/commands/trade_cmd.py`**

Replace the entire file with the following (preserves all existing commands, adds new ones):

```python
"""Trading execution commands — paper and live trading with risk management."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading_cli.core.base_trader import BaseTrader
from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, Market, registry
from trading_cli.core.tushare_provider import TushareProvider
from trading_cli.core.order import OrderSide, OrderType
from trading_cli.core.paper_trader import PaperTrader
from trading_cli.core.trade_logger import TradeLogger

console = Console()

# Session-level trader singletons
_paper_trader: Optional[PaperTrader] = None
_live_trader = None  # RealTrader — lazy import to avoid ib_insync dependency

_logger = TradeLogger()


def _get_trader(live: bool = False) -> BaseTrader:
    global _paper_trader, _live_trader
    if live:
        if _live_trader is None:
            from trading_cli.core.live_trader import RealTrader

            _live_trader = RealTrader()
        return _live_trader
    if _paper_trader is None:
        _paper_trader = PaperTrader()
    return _paper_trader


def _ensure_providers() -> None:
    if not registry.list_providers():
        config = get_config()
        registry.register(TushareProvider(config.data.tushare))


def _fetch_price(symbol: str) -> Optional[float]:
    """Fetch the latest closing price for a symbol."""
    _ensure_providers()
    config = get_config()
    dp = registry.get(config.data.default_provider)
    request = DataFetchRequest(
        symbol=symbol,
        start_date=date.today() - timedelta(days=10),
        end_date=date.today(),
    )
    try:
        result = dp.fetch_stock_daily(request)
        if not result.is_empty:
            return float(result.data.iloc[-1]["close"])
    except Exception:
        pass
    return None


def _confirm_live(symbol: str, side: str, qty: int, price: Optional[float]) -> bool:
    """Show live-order warning and prompt for confirmation. Returns True if confirmed."""
    price_str = f"@ ${price:.2f}" if price else "@ MARKET"
    console.print(f"\n[bold red]⚠  LIVE ORDER — REAL MONEY[/bold red]")
    console.print(f"  {side} {symbol} × {qty} {price_str}")
    return click.confirm("Confirm?", default=False)


@click.group()
def trade():
    """💹 Trading Execution — paper trading with risk management."""
    pass


# ---- order sub-group ----


@trade.group()
def order():
    """Manage orders."""
    pass


@order.command("buy")
@click.argument("symbol")
@click.option("--qty", "-q", type=int, required=True, help="Number of shares.")
@click.option(
    "--price", "-p", type=float, default=None, help="Limit price (omit for market order)."
)
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
@click.option("--yes", "skip_confirm", is_flag=True, default=False, help="Skip confirmation (live mode only).")
def order_buy(symbol: str, qty: int, price: Optional[float], live: bool, skip_confirm: bool):
    """Place a buy order.

    Examples:

        trading-cli trade order buy 000001.SZ --qty 1000

        trading-cli trade order buy AAPL --qty 100 --live
    """
    if live and not skip_confirm:
        if not _confirm_live(symbol, "BUY", qty, price):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    trader = _get_trader(live)
    current_price = price or _fetch_price(symbol)
    if current_price is None:
        console.print(f"[red]Cannot determine price for {symbol}.[/red]")
        return

    order_type = OrderType.LIMIT if price else OrderType.MARKET
    result = trader.place_order(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        order_type=order_type,
        price=price,
        current_price=current_price,
    )

    mode = "live" if live else "paper"
    if not live:
        _logger.log(result, mode=mode)

    if result.status.value == "FILLED":
        console.print(
            f"[green]✓ BUY FILLED[/green] [{mode}] {symbol} × {qty} @ ${result.filled_price:.2f}"
        )
    elif result.status.value == "REJECTED":
        console.print(f"[red]✗ REJECTED:[/red] {result.message}")
    else:
        console.print(f"[yellow]⏳ {result.status.value}[/yellow] Order {result.id} placed.")


@order.command("sell")
@click.argument("symbol")
@click.option(
    "--qty", "-q", type=int, default=0, help="Shares to sell (0 = close entire position)."
)
@click.option("--price", "-p", type=float, default=None, help="Limit price.")
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
@click.option("--yes", "skip_confirm", is_flag=True, default=False, help="Skip confirmation (live mode only).")
def order_sell(symbol: str, qty: int, price: Optional[float], live: bool, skip_confirm: bool):
    """Place a sell order.

    Examples:

        trading-cli trade order sell 000001.SZ --qty 500

        trading-cli trade order sell AAPL --live --yes
    """
    trader = _get_trader(live)
    current_price = price or _fetch_price(symbol)
    if current_price is None:
        console.print(f"[red]Cannot determine price for {symbol}.[/red]")
        return

    # Default: close entire position (paper mode only — live uses IB positions)
    if qty == 0 and not live:
        pos = trader.account.positions.get(symbol.upper())  # type: ignore[attr-defined]
        if not pos:
            console.print(f"[yellow]No position in {symbol} to sell.[/yellow]")
            return
        qty = pos.quantity

    if live and not skip_confirm:
        if not _confirm_live(symbol, "SELL", qty, price):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    result = trader.place_order(
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=qty,
        order_type=OrderType.LIMIT if price else OrderType.MARKET,
        price=price,
        current_price=current_price,
    )

    mode = "live" if live else "paper"
    if not live:
        _logger.log(result, mode=mode)

    if result.status.value == "FILLED":
        console.print(
            f"[green]✓ SELL FILLED[/green] [{mode}] {symbol} × {qty} @ ${result.filled_price:.2f}"
        )
    elif result.status.value == "REJECTED":
        console.print(f"[red]✗ REJECTED:[/red] {result.message}")


@order.command("list")
@click.option(
    "--status", "-s",
    type=click.Choice(["all", "open", "filled", "cancelled"]),
    default="all",
)
def order_list(status: str):
    """List orders."""
    trader = _get_trader(live=False)
    orders = trader.account.orders  # type: ignore[attr-defined]

    if status == "open":
        orders = trader.account.get_open_orders()  # type: ignore[attr-defined]
    elif status == "filled":
        orders = trader.account.get_filled_orders()  # type: ignore[attr-defined]
    elif status == "cancelled":
        orders = [o for o in orders if o.status.value == "CANCELLED"]

    if not orders:
        console.print("[yellow]No orders.[/yellow]")
        return

    table = Table(title="Orders")
    table.add_column("ID", style="cyan")
    table.add_column("Symbol", style="bold")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Status")
    table.add_column("Time", style="dim")

    for o in orders:
        side_c = "green" if o.side == OrderSide.BUY else "red"
        status_c = {
            "FILLED": "green",
            "REJECTED": "red",
            "CANCELLED": "dim",
            "PENDING": "yellow",
        }.get(o.status.value, "white")
        p = (
            f"${o.filled_price:.2f}"
            if o.filled_price
            else (f"${o.price:.2f}" if o.price else "MKT")
        )
        table.add_row(
            o.id,
            o.symbol,
            f"[{side_c}]{o.side.value}[/{side_c}]",
            str(o.quantity),
            p,
            f"[{status_c}]{o.status.value}[/{status_c}]",
            o.created_at.strftime("%H:%M:%S"),
        )
    console.print(table)


@order.command("cancel")
@click.argument("order_id")
def order_cancel(order_id: str):
    """Cancel a pending order."""
    trader = _get_trader(live=False)
    if trader.cancel_order(order_id):
        console.print(f"[green]✓[/green] Order {order_id} cancelled.")
    else:
        console.print(f"[red]Order {order_id} not found or not cancellable.[/red]")


# ---- position sub-group ----


@trade.group()
def position():
    """Manage positions."""
    pass


@position.command("list")
def position_list():
    """List all open positions."""
    trader = _get_trader(live=False)
    positions = trader.account.positions  # type: ignore[attr-defined]

    if not positions:
        console.print("[yellow]No open positions.[/yellow]")
        return

    table = Table(title="Open Positions", show_lines=True)
    table.add_column("Symbol", style="cyan bold")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Mkt Value", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("P&L%", justify="right")

    for sym, p in positions.items():
        c = "green" if p.unrealized_pnl >= 0 else "red"
        table.add_row(
            sym,
            f"{p.quantity:,}",
            f"${p.avg_cost:.2f}",
            f"${p.current_price:.2f}",
            f"${p.market_value:,.2f}",
            f"[{c}]${p.unrealized_pnl:,.2f}[/{c}]",
            f"[{c}]{p.unrealized_pnl_pct:+.2f}%[/{c}]",
        )
    console.print(table)


@position.command("close")
@click.argument("symbol")
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
@click.option("--yes", "skip_confirm", is_flag=True, default=False, help="Skip confirmation.")
def position_close(symbol: str, live: bool, skip_confirm: bool):
    """Close an entire position at market price."""
    if live and not skip_confirm:
        if not _confirm_live(symbol, "SELL (close)", 0, None):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    trader = _get_trader(live)
    current_price = _fetch_price(symbol)
    if current_price is None:
        console.print(f"[red]Cannot determine price for {symbol}.[/red]")
        return

    order = trader.close_position(symbol, current_price)
    if order is None:
        console.print(f"[yellow]No position in {symbol}.[/yellow]")
    elif order.status.value == "FILLED":
        console.print(
            f"[green]✓ Position closed[/green] {symbol} × {order.filled_quantity} @ ${order.filled_price:.2f}"
        )
    else:
        console.print(f"[red]Close failed:[/red] {order.message}")


# ---- account ----


@trade.command()
def account():
    """Show account summary."""
    trader = _get_trader(live=False)
    a = trader.account  # type: ignore[attr-defined]

    pnl_c = "green" if a.total_pnl >= 0 else "red"
    info = Table(show_header=False, box=None)
    info.add_column("k", style="dim", width=18)
    info.add_column("v", justify="right")
    info.add_row("Account ID", a.account_id)
    info.add_row("Initial Capital", f"${a.initial_capital:,.2f}")
    info.add_row("Cash", f"${a.cash:,.2f}")
    info.add_row("Market Value", f"${a.total_market_value:,.2f}")
    info.add_row("Total Equity", f"[bold]${a.total_equity:,.2f}[/bold]")
    info.add_row(
        "P&L", f"[{pnl_c}]${a.total_pnl:,.2f} ({a.total_pnl_pct:+.2f}%)[/{pnl_c}]"
    )
    info.add_row("Open Positions", str(a.position_count))
    info.add_row("Total Orders", str(len(a.orders)))

    console.print()
    console.print(Panel(info, title="[bold]Paper Trading Account[/bold]", border_style="blue"))
    console.print()


# ---- risk ----


@trade.command()
def risk():
    """Run portfolio risk check."""
    trader = _get_trader(live=False)
    result = trader.check_risk()

    if result.passed:
        console.print("[green]✓ All risk checks passed.[/green]")
    else:
        console.print("[red]⚠ Risk violations detected:[/red]")
        for v in result.violations:
            console.print(f"  [red]•[/red] {v}")

    rc = trader.risk_engine.config  # type: ignore[attr-defined]
    console.print(
        f"\n[dim]Risk limits: max position {rc.max_position_pct:.0%} | "
        f"max positions {rc.max_positions} | "
        f"stop loss {rc.max_single_loss_pct}% | "
        f"daily loss limit {rc.max_daily_loss_pct}% | "
        f"cash reserve {rc.min_cash_reserve_pct:.0%}[/dim]"
    )


# ---- emergency sub-group ----


@trade.group()
def emergency():
    """🚨 Emergency operations."""
    pass


@emergency.command("stop")
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
def emergency_stop(live: bool):
    """Cancel all orders and close all positions immediately.

    This command does NOT ask for confirmation — it acts immediately.

    Examples:

        trading-cli trade emergency stop           (paper mode — safe simulation)

        trading-cli trade emergency stop --live    (REAL MONEY — acts instantly)
    """
    trader = _get_trader(live)

    if live:
        console.print("[bold red]🚨 EMERGENCY STOP — LIVE MODE — REAL MONEY[/bold red]")
    else:
        console.print("[bold yellow]🚨 Emergency Stop (paper mode)[/bold yellow]")

    # Collect prices for paper mode (uses current_price on positions)
    prices: dict[str, float] = {}
    if not live:
        paper = trader  # type: ignore[assignment]
        for sym, pos in paper.account.positions.items():  # type: ignore[attr-defined]
            prices[sym] = pos.current_price
        if not paper.account.positions:  # type: ignore[attr-defined]
            console.print("[yellow]No open positions to close.[/yellow]")
            return

    orders = trader.emergency_stop(prices)

    if not orders:
        console.print("[green]✓ No positions were open.[/green]")
        return

    table = Table(title="Emergency Stop Results")
    table.add_column("Symbol", style="cyan")
    table.add_column("Qty", justify="right")
    table.add_column("Status")

    for o in orders:
        status_c = "green" if o.status.value == "FILLED" else "red"
        table.add_row(o.symbol, str(o.quantity), f"[{status_c}]{o.status.value}[/{status_c}]")

    console.print(table)
    console.print(f"[green]✓ Emergency stop complete — {len(orders)} position(s) closed.[/green]")
```

- [ ] **Step 4: Run the new CLI tests**

```bash
python -m pytest tests/test_cli.py -k "emergency_stop or live_requires" -v
```

Expected: `2 passed`

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ --tb=short -q
```

Expected: 177 passed (no regressions).

- [ ] **Step 6: black + mypy**

```bash
python -m black trading_cli/commands/trade_cmd.py trading_cli/core/
python -m mypy trading_cli/ --ignore-missing-imports
```

Expected: `black` — reformatted or already clean. `mypy` — `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add trading_cli/commands/trade_cmd.py
git commit -m "feat: trade_cmd --live/--yes flags and emergency stop command"
```

---

## Task 5: Security Audit

**Files:** Read-only scan + targeted fixes if needed

- [ ] **Step 1: Grep for hardcoded secrets**

```bash
cd /Users/macbot/workspace/daily-engineer/trading-wisdom-cli
grep -rn "tushare.*token\s*=\s*['\"].\+" trading_cli/ || echo "OK: no hardcoded Tushare token"
grep -rn "password\s*=\s*['\"].\+" trading_cli/ || echo "OK: no hardcoded password"
grep -rn "secret\s*=\s*['\"].\+" trading_cli/ || echo "OK: no hardcoded secret"
```

Expected: all three print `OK: no hardcoded ...`

- [ ] **Step 2: Verify IB credentials use env vars**

```bash
grep -n "IB_HOST\|IB_PORT\|IB_CLIENT_ID" trading_cli/core/live_trader.py
```

Expected: 3 lines showing `os.environ.get("IB_HOST"...)` etc. in `__init__`.

- [ ] **Step 3: Verify `--live` defaults to False everywhere**

```bash
grep -n "\"--live\"\|'--live'" trading_cli/commands/trade_cmd.py
```

Expected: every `--live` option line shows `default=False`.

- [ ] **Step 4: Verify token not logged**

```bash
grep -n "token\|password\|secret" trading_cli/core/trade_logger.py
```

Expected: none of these words appear in `trade_logger.py`.

- [ ] **Step 5: Verify Tushare token comes from config, not code**

```bash
grep -rn "TushareProvider" trading_cli/ | grep -v "^Binary\|test_"
```

Expected: `TushareProvider` is only constructed with `config.data.tushare` (the config object), never with a raw string token.

- [ ] **Step 6: Run full suite one final time**

```bash
python -m pytest tests/ -q
```

Expected: 177 passed, 0 failed.

- [ ] **Step 7: Commit audit results**

```bash
git add -A
git commit -m "audit: Phase 5 security audit — env vars, no hardcoded secrets, token not logged"
```

---

## Final Verification

After all tasks complete, verify all acceptance criteria:

```bash
# 1. All tests pass
python -m pytest tests/ -q
# Expected: 177 passed

# 2. CLI help shows emergency subcommand
trading-cli trade emergency --help
# Expected: shows "stop" subcommand

# 3. black clean
python -m black --check trading_cli/
# Expected: "All done!"

# 4. mypy clean
python -m mypy trading_cli/ --ignore-missing-imports
# Expected: "Success: no issues found"

# 5. Log file is created after paper trade
trading-cli trade order buy TEST --qty 1
ls ~/.trading-cli/trade_log.jsonl
tail -1 ~/.trading-cli/trade_log.jsonl
# Expected: JSON line with mode=paper, no token fields
```
