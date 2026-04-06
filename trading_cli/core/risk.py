"""Risk management engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from trading_cli.core.order import Account, Order, OrderSide


@dataclass
class RiskCheckResult:
    """Result of a risk check."""

    passed: bool
    violations: list[str]

    @property
    def summary(self) -> str:
        if self.passed:
            return "All risk checks passed"
        return "; ".join(self.violations)


class RiskConfig:
    """Risk management configuration."""

    def __init__(
        self,
        max_position_pct: float = 0.25,
        max_positions: int = 10,
        max_single_loss_pct: float = 2.0,
        max_daily_loss_pct: float = 5.0,
        min_cash_reserve_pct: float = 0.10,
    ):
        self.max_position_pct = max_position_pct       # max % of equity per position
        self.max_positions = max_positions               # max number of positions
        self.max_single_loss_pct = max_single_loss_pct   # max loss % per trade before stop
        self.max_daily_loss_pct = max_daily_loss_pct     # max daily loss % before halt
        self.min_cash_reserve_pct = min_cash_reserve_pct # min cash reserve as % of equity


class RiskEngine:
    """Pre-trade and portfolio-level risk checks."""

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()

    def check_order(self, order: Order, account: Account, current_price: float) -> RiskCheckResult:
        """Run all pre-trade risk checks on an order."""
        violations: list[str] = []

        if order.side == OrderSide.BUY:
            self._check_buying_power(order, account, current_price, violations)
            self._check_position_concentration(order, account, current_price, violations)
            self._check_max_positions(order, account, violations)
            self._check_cash_reserve(order, account, current_price, violations)

        if order.side == OrderSide.SELL:
            self._check_sell_quantity(order, account, violations)

        return RiskCheckResult(passed=len(violations) == 0, violations=violations)

    def check_portfolio(self, account: Account) -> RiskCheckResult:
        """Run portfolio-level risk checks."""
        violations: list[str] = []

        # Daily P&L check
        daily_pnl_pct = account.total_pnl_pct
        if daily_pnl_pct < -self.config.max_daily_loss_pct:
            violations.append(
                f"Daily loss {daily_pnl_pct:.1f}% exceeds limit -{self.config.max_daily_loss_pct}%"
            )

        # Position count
        if account.position_count > self.config.max_positions:
            violations.append(
                f"Position count {account.position_count} exceeds max {self.config.max_positions}"
            )

        # Cash reserve
        if account.total_equity > 0:
            cash_pct = account.cash / account.total_equity
            if cash_pct < self.config.min_cash_reserve_pct:
                violations.append(
                    f"Cash reserve {cash_pct:.1%} below minimum {self.config.min_cash_reserve_pct:.0%}"
                )

        # Per-position concentration
        for sym, pos in account.positions.items():
            if account.total_equity > 0:
                concentration = pos.market_value / account.total_equity
                if concentration > self.config.max_position_pct:
                    violations.append(
                        f"{sym} concentration {concentration:.1%} exceeds max {self.config.max_position_pct:.0%}"
                    )

        # Per-position loss
        for sym, pos in account.positions.items():
            if pos.unrealized_pnl_pct < -self.config.max_single_loss_pct:
                violations.append(
                    f"{sym} loss {pos.unrealized_pnl_pct:.1f}% exceeds stop limit -{self.config.max_single_loss_pct}%"
                )

        return RiskCheckResult(passed=len(violations) == 0, violations=violations)

    def suggest_stop_loss(self, entry_price: float) -> float:
        """Calculate suggested stop-loss price."""
        return entry_price * (1 - self.config.max_single_loss_pct / 100)

    def max_shares(self, account: Account, price: float) -> int:
        """Calculate max shares affordable under risk limits."""
        max_by_concentration = account.total_equity * self.config.max_position_pct
        reserve = account.total_equity * self.config.min_cash_reserve_pct
        max_by_cash = max(account.cash - reserve, 0)
        max_value = min(max_by_concentration, max_by_cash)
        return int(max_value / price) if price > 0 else 0

    # --- private checks ---

    def _check_buying_power(self, order: Order, account: Account, price: float, v: list[str]):
        cost = order.quantity * price * (1 + account.commission_rate + account.slippage)
        if cost > account.cash:
            v.append(f"Insufficient cash: need ¥{cost:,.0f}, have ¥{account.cash:,.0f}")

    def _check_position_concentration(self, order: Order, account: Account, price: float, v: list[str]):
        new_value = order.quantity * price
        existing = account.positions.get(order.symbol)
        if existing:
            new_value += existing.market_value
        if account.total_equity > 0 and new_value / account.total_equity > self.config.max_position_pct:
            v.append(
                f"Position {order.symbol} would be {new_value / account.total_equity:.1%} "
                f"of equity, exceeds {self.config.max_position_pct:.0%} limit"
            )

    def _check_max_positions(self, order: Order, account: Account, v: list[str]):
        if order.symbol not in account.positions and account.position_count >= self.config.max_positions:
            v.append(f"Max positions ({self.config.max_positions}) reached")

    def _check_cash_reserve(self, order: Order, account: Account, price: float, v: list[str]):
        cost = order.quantity * price
        remaining_cash = account.cash - cost
        if account.total_equity > 0 and remaining_cash / account.total_equity < self.config.min_cash_reserve_pct:
            v.append(
                f"Order would reduce cash reserve below {self.config.min_cash_reserve_pct:.0%} minimum"
            )

    def _check_sell_quantity(self, order: Order, account: Account, v: list[str]):
        pos = account.positions.get(order.symbol)
        if not pos:
            v.append(f"No position in {order.symbol} to sell")
        elif order.quantity > pos.quantity:
            v.append(f"Sell qty {order.quantity} > position qty {pos.quantity}")
