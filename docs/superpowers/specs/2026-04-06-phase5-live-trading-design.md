# Phase 5 — Live Trading Design Spec

**Date:** 2026-04-06
**Author:** Sasa (CFO) + Claude
**Status:** Approved

---

## Overview

Phase 5 adds IBKR live trading execution to the CLI, built on top of the existing `PaperTrader` infrastructure. The goal is a safe, auditable path from paper to live trading for HK/US markets — without touching CN (A-share) execution, which is deferred to Phase 6+ (vnpy/CTP).

---

## Scope

- IBKR live order execution via `ib_insync` (HK + US markets only)
- `BaseTrader` abstract class to unify paper and live interfaces
- Safety layer: `--live` flag, `--yes` bypass, emergency stop command
- JSON Lines trade audit log
- Security audit: env vars, no hardcoded credentials, no token logging
- ≥10 unit tests (mock ib_insync), all existing 20+ paper trader tests still passing

**Out of scope:** CTP/vnpy (A-shares), async architecture, order management UI, real-time P&L streaming.

---

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `trading_cli/core/base_trader.py` | Abstract `BaseTrader` interface |
| `trading_cli/core/live_trader.py` | `RealTrader` (ib_insync implementation) |
| `trading_cli/core/trade_logger.py` | JSON Lines audit log writer |
| `tests/test_live_trader.py` | Unit tests with mocked ib_insync |

### Modified Files

| File | Change |
|------|--------|
| `trading_cli/core/paper_trader.py` | Inherit `BaseTrader`, add `emergency_stop` |
| `trading_cli/commands/trade_cmd.py` | Add `--live`, `--yes` flags; add `emergency stop` command |

---

## Section 1: BaseTrader Interface

```python
# trading_cli/core/base_trader.py
from abc import ABC, abstractmethod
from typing import Optional
from trading_cli.core.order import Order, OrderSide, OrderType
from trading_cli.core.risk import RiskCheckResult

class BaseTrader(ABC):
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

`PaperTrader` already implements all methods except `emergency_stop`. Adding `(BaseTrader)` inheritance requires only adding `emergency_stop`.

---

## Section 2: RealTrader Implementation

`RealTrader` wraps `ib_insync.IB` with synchronous blocking calls.

**Connection:** Lazy — connects on first `place_order` call. Config from env vars:
- `IB_HOST` (default: `127.0.0.1`)
- `IB_PORT` (default: `7497` for TWS live, `7496` for paper)
- `IB_CLIENT_ID` (default: `1`)

**Order flow:**
1. Build `ib_insync.Contract` (Stock, SEHK/HKD for HK; Stock, SMART/USD for US)
2. `ib.qualifyContracts(contract)`
3. Build `ib_insync.Order` (LmtOrder or MktOrder)
4. `trade = ib.placeOrder(contract, ib_order)`
5. `ib.sleep(timeout)` — wait for fill confirmation (default 10s)
6. Map IB status → system `OrderStatus` and return system `Order`

**IB status mapping:**

| IB Status | System Status |
|-----------|--------------|
| `Filled` | `FILLED` |
| `Cancelled` | `CANCELLED` |
| `Inactive` | `REJECTED` |
| `PreSubmitted`, `Submitted` | `PENDING` |

**`cancel_order`:** `RealTrader` keeps an internal `_trades: dict[str, ib_insync.Trade]` mapping system `order.id → ib Trade`. `cancel_order(order_id)` looks up the trade and calls `ib.cancelOrder(trade.order)`.

**`emergency_stop(prices)`:**
1. `ib.reqGlobalCancel()` — cancel all open orders on the account
2. `ib.sleep(1)` — allow cancellations to propagate
3. For each position in `ib.positions()`: place market sell order
4. Log all results to `TradeLogger`
5. Return list of system `Order` objects

**Contract construction** (mirrors existing `IBProvider._live_fetch`):
```python
if market == "HK":
    contract = Stock(symbol.replace(".HK", ""), "SEHK", "HKD")
else:
    contract = Stock(symbol, "SMART", "USD")
```

---

## Section 3: Safety Layer

### `--live` and `--yes` flags

Applied to `trade order buy`, `trade order sell`, `trade position close`:

```
--live    Use real IBKR account (default: paper trading)
--yes     Skip confirmation prompt (for automation; only valid with --live)
```

**Live mode confirmation flow:**
```
⚠ LIVE ORDER — REAL MONEY
  BUY AAPL × 100 @ MARKET
  Estimated value: $18,500

Confirm? [y/N]:
```
- `--yes` suppresses the prompt and proceeds directly
- Paper mode: no prompt, no warning

### `trade emergency stop` command

```
trading-cli trade emergency stop [--live]
```

- Prints all open positions before executing
- Does **not** ask for confirmation (emergency scenario)
- Executes: cancel all orders → market-sell all positions
- Prints per-order result (symbol / qty / status)
- In paper mode: uses `PaperTrader.emergency_stop()` (safe simulation)

---

## Section 4: TradeLogger

**File:** `~/.trading-cli/trade_log.jsonl`
**Format:** One JSON object per line

```json
{
  "timestamp": "2026-04-06T10:23:01.123456",
  "mode": "live",
  "symbol": "AAPL",
  "side": "BUY",
  "quantity": 100,
  "order_type": "MARKET",
  "price": null,
  "filled_price": 185.10,
  "status": "FILLED",
  "order_id": "ORD-00001",
  "account_id_suffix": "1234"
}
```

**Security rules:**
- `account_id_suffix`: last 4 chars of IB account ID only
- IB host/port/client_id: not logged
- API tokens (Tushare etc): not logged
- `ib_insync` library version: logged once at session start

**Written for both paper and live modes** (mode field distinguishes them).

---

## Section 5: Security Audit Checklist

| Check | Target | Status |
|-------|--------|--------|
| IB credentials from env vars | `IB_HOST`, `IB_PORT`, `IB_CLIENT_ID` | To implement |
| No hardcoded secrets | All source files | To verify |
| Tushare token from config, not code | `config.yaml` | Already done |
| `--live` default is paper (dry-run) | `trade order buy/sell` | To implement |
| Token not in trade log | `TradeLogger` | To implement |
| Token not in application logs | All commands | To verify |

---

## Section 6: Tests (`test_live_trader.py`)

All tests mock `ib_insync` via `monkeypatch` — no real IB connection needed.

| # | Test |
|---|------|
| 1 | `place_order` BUY → FILLED |
| 2 | `place_order` SELL → FILLED |
| 3 | `place_order` → REJECTED (IB returns Inactive) |
| 4 | `cancel_order` success |
| 5 | `cancel_order` nonexistent ID → False |
| 6 | `close_position` with open position |
| 7 | `close_position` no position → None |
| 8 | `emergency_stop` order: cancel-first then close-positions |
| 9 | `emergency_stop` no positions → empty list |
| 10 | ib_insync not installed → RuntimeError |
| 11 | IB connection failure → RuntimeError |
| 12 | `TradeLogger` writes correct fields, no token in output |

**Existing tests:** All 20 `TestPaperTrader` + `TestRiskEngine` tests must continue passing after `PaperTrader` inherits `BaseTrader`.

---

## Commit Plan

| Step | Commit message |
|------|---------------|
| 1 | `feat: add BaseTrader ABC and update PaperTrader to inherit it` |
| 2 | `feat: add TradeLogger (JSON Lines audit log)` |
| 3 | `feat: add RealTrader (ib_insync live execution)` |
| 4 | `feat: trade_cmd --live/--yes flags and emergency stop command` |
| 5 | `test: add test_live_trader.py (12 tests, mock ib_insync)` |
| 6 | `audit: Phase 5 security audit — env vars, no hardcoded secrets` |
