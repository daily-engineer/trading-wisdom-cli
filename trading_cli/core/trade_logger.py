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
