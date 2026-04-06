"""Price monitoring engine and alert rules."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field


class AlertCondition(str, Enum):
    """Supported alert condition types."""

    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    CHANGE_PCT_ABOVE = "change_pct_above"
    CHANGE_PCT_BELOW = "change_pct_below"
    VOLUME_ABOVE = "volume_above"
    RSI_ABOVE = "rsi_above"
    RSI_BELOW = "rsi_below"


class AlertRule(BaseModel):
    """A single alert rule."""

    id: str
    symbol: str
    condition: AlertCondition
    threshold: float
    message: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    triggered: bool = False
    triggered_at: Optional[datetime] = None

    def check(self, market_data: dict) -> bool:
        """Evaluate this rule against current market data. Returns True if triggered."""
        value = self._extract_value(market_data)
        if value is None:
            return False

        fired = False
        if self.condition in (
            AlertCondition.PRICE_ABOVE,
            AlertCondition.CHANGE_PCT_ABOVE,
            AlertCondition.VOLUME_ABOVE,
            AlertCondition.RSI_ABOVE,
        ):
            fired = value > self.threshold
        elif self.condition in (
            AlertCondition.PRICE_BELOW,
            AlertCondition.CHANGE_PCT_BELOW,
            AlertCondition.RSI_BELOW,
        ):
            fired = value < self.threshold

        if fired and not self.triggered:
            self.triggered = True
            self.triggered_at = datetime.now()
        return fired

    def _extract_value(self, data: dict) -> Optional[float]:
        mapping = {
            AlertCondition.PRICE_ABOVE: "close",
            AlertCondition.PRICE_BELOW: "close",
            AlertCondition.CHANGE_PCT_ABOVE: "change_pct",
            AlertCondition.CHANGE_PCT_BELOW: "change_pct",
            AlertCondition.VOLUME_ABOVE: "vol",
            AlertCondition.RSI_ABOVE: "rsi",
            AlertCondition.RSI_BELOW: "rsi",
        }
        key = mapping.get(self.condition)
        return data.get(key) if key else None


class AlertManager:
    """Manages alert rules."""

    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._counter = 0

    def add_rule(
        self,
        symbol: str,
        condition: AlertCondition,
        threshold: float,
        message: str = "",
    ) -> AlertRule:
        self._counter += 1
        rule_id = f"alert-{self._counter:03d}"
        rule = AlertRule(
            id=rule_id,
            symbol=symbol.upper(),
            condition=condition,
            threshold=threshold,
            message=message or f"{symbol} {condition.value} {threshold}",
        )
        self._rules[rule_id] = rule
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        return self._rules.pop(rule_id, None) is not None

    def check_all(self, symbol: str, market_data: dict) -> list[AlertRule]:
        """Check all rules for a symbol. Returns list of newly triggered rules."""
        triggered = []
        for rule in self._rules.values():
            if rule.symbol == symbol.upper() and not rule.triggered:
                if rule.check(market_data):
                    triggered.append(rule)
        return triggered

    def list_rules(self, symbol: Optional[str] = None) -> list[AlertRule]:
        rules = list(self._rules.values())
        if symbol:
            rules = [r for r in rules if r.symbol == symbol.upper()]
        return rules

    def clear_triggered(self) -> int:
        count = 0
        for rule in self._rules.values():
            if rule.triggered:
                rule.triggered = False
                rule.triggered_at = None
                count += 1
        return count


class MarketSnapshot(BaseModel):
    """Point-in-time snapshot of a symbol's market data."""

    symbol: str
    close: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    vol: float = 0.0
    amount: float = 0.0
    change_pct: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_dataframe_row(
        cls, symbol: str, row: pd.Series, prev_close: Optional[float] = None
    ) -> MarketSnapshot:
        close = float(row.get("close", 0))
        prev = prev_close or float(row.get("open", close))
        change_pct = ((close - prev) / prev * 100) if prev else 0.0
        return cls(
            symbol=symbol,
            close=close,
            open=float(row.get("open", 0)),
            high=float(row.get("high", 0)),
            low=float(row.get("low", 0)),
            vol=float(row.get("vol", 0)),
            amount=float(row.get("amount", 0)),
            change_pct=round(change_pct, 2),
        )
