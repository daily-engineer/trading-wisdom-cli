"""Report generation engine."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Optional

import json
import pandas as pd
from pydantic import BaseModel, Field


class PortfolioPosition(BaseModel):
    """A position in the portfolio."""

    symbol: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    market: str = "CN"

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def pnl_pct(self) -> float:
        return (self.pnl / self.cost_basis * 100) if self.cost_basis else 0.0


class PortfolioSummary(BaseModel):
    """Portfolio-level summary."""

    positions: list[PortfolioPosition] = Field(default_factory=list)
    cash: float = 0.0
    generated_at: datetime = Field(default_factory=datetime.now)

    @property
    def total_market_value(self) -> float:
        return sum(p.market_value for p in self.positions)

    @property
    def total_cost(self) -> float:
        return sum(p.cost_basis for p in self.positions)

    @property
    def total_pnl(self) -> float:
        return sum(p.pnl for p in self.positions)

    @property
    def total_pnl_pct(self) -> float:
        return (self.total_pnl / self.total_cost * 100) if self.total_cost else 0.0

    @property
    def total_equity(self) -> float:
        return self.total_market_value + self.cash

    @property
    def position_count(self) -> int:
        return len(self.positions)


class PerformanceMetrics(BaseModel):
    """Performance report metrics."""

    period_start: date
    period_end: date
    starting_equity: float
    ending_equity: float
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0

    @property
    def return_pct(self) -> float:
        return (
            (self.ending_equity - self.starting_equity) / self.starting_equity * 100
            if self.starting_equity
            else 0.0
        )


class ReportGenerator:
    """Generates and exports trading reports."""

    REPORTS_DIR = Path.home() / ".trading-wisdom" / "reports"

    def __init__(self) -> None:
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def generate_portfolio_report(self, summary: PortfolioSummary) -> dict:
        """Generate a portfolio report dict."""
        return {
            "type": "portfolio",
            "generated_at": summary.generated_at.isoformat(),
            "equity": summary.total_equity,
            "cash": summary.cash,
            "market_value": summary.total_market_value,
            "total_pnl": summary.total_pnl,
            "total_pnl_pct": round(summary.total_pnl_pct, 2),
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_cost": p.avg_cost,
                    "current_price": p.current_price,
                    "market_value": round(p.market_value, 2),
                    "pnl": round(p.pnl, 2),
                    "pnl_pct": round(p.pnl_pct, 2),
                }
                for p in summary.positions
            ],
        }

    def generate_performance_report(self, metrics: PerformanceMetrics) -> dict:
        """Generate a performance report dict."""
        return {
            "type": "performance",
            "period": f"{metrics.period_start} ~ {metrics.period_end}",
            "starting_equity": metrics.starting_equity,
            "ending_equity": round(metrics.ending_equity, 2),
            "return_pct": round(metrics.return_pct, 2),
            "total_trades": metrics.total_trades,
            "win_rate": round(metrics.win_rate, 2),
            "total_pnl": round(metrics.total_pnl, 2),
            "max_drawdown": round(metrics.max_drawdown, 2),
            "sharpe_ratio": round(metrics.sharpe_ratio, 2),
            "best_trade": round(metrics.best_trade_pnl, 2),
            "worst_trade": round(metrics.worst_trade_pnl, 2),
        }

    def export_json(self, report: dict, filename: Optional[str] = None) -> Path:
        """Export report to JSON file."""
        name = (
            filename
            or f"report_{report['type']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        path = self.REPORTS_DIR / name
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return path

    def export_csv(self, data: list[dict], filename: str) -> Path:
        """Export data rows to CSV."""
        path = self.REPORTS_DIR / filename
        df = pd.DataFrame(data)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def list_reports(self) -> list[Path]:
        """List saved report files."""
        return sorted(self.REPORTS_DIR.glob("report_*"), reverse=True)
