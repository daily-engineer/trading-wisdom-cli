"""Reporting commands."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import json
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading_cli.core.reporter import (
    PortfolioPosition,
    PortfolioSummary,
    PerformanceMetrics,
    ReportGenerator,
)

console = Console()
_generator = ReportGenerator()


@click.group()
def report():
    """📋 Reporting — generate and export trading reports."""
    pass


@report.command()
@click.option(
    "--file",
    "-f",
    "portfolio_file",
    type=click.Path(exists=True),
    default=None,
    help="Portfolio JSON file path.",
)
def portfolio(portfolio_file: str | None):
    """Display portfolio summary report.

    Without --file, shows a demo portfolio. Provide a JSON file for real data.

    Portfolio JSON format:

        {"cash": 50000, "positions": [{"symbol": "000001.SZ", "quantity": 1000, "avg_cost": 10.5, "current_price": 11.2}]}
    """
    if portfolio_file:
        with open(portfolio_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        positions = [PortfolioPosition(**p) for p in raw.get("positions", [])]
        summary = PortfolioSummary(positions=positions, cash=raw.get("cash", 0))
    else:
        # Demo portfolio
        summary = PortfolioSummary(
            cash=50000,
            positions=[
                PortfolioPosition(
                    symbol="000001.SZ",
                    quantity=1000,
                    avg_cost=10.50,
                    current_price=11.12,
                ),
                PortfolioPosition(
                    symbol="600519.SH",
                    quantity=100,
                    avg_cost=1680.00,
                    current_price=1720.50,
                ),
                PortfolioPosition(
                    symbol="000858.SZ",
                    quantity=500,
                    avg_cost=135.20,
                    current_price=128.80,
                ),
            ],
        )

    report_data = _generator.generate_portfolio_report(summary)

    # Header
    pnl_color = "green" if summary.total_pnl >= 0 else "red"
    header = Table(show_header=False, box=None)
    header.add_column("k", style="dim", width=18)
    header.add_column("v", justify="right")
    header.add_row("Total Equity", f"¥{summary.total_equity:,.2f}")
    header.add_row("Market Value", f"¥{summary.total_market_value:,.2f}")
    header.add_row("Cash", f"¥{summary.cash:,.2f}")
    header.add_row(
        "Total P&L",
        f"[{pnl_color}]¥{summary.total_pnl:,.2f} ({summary.total_pnl_pct:+.2f}%)[/{pnl_color}]",
    )
    header.add_row("Positions", f"{summary.position_count}")

    console.print()
    console.print(
        Panel(header, title="[bold]Portfolio Summary[/bold]", border_style="blue")
    )

    # Positions table
    table = Table(title="Positions", show_lines=True)
    table.add_column("Symbol", style="cyan bold")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Mkt Value", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("P&L%", justify="right")

    for p in summary.positions:
        c = "green" if p.pnl >= 0 else "red"
        table.add_row(
            p.symbol,
            f"{p.quantity:,}",
            f"{p.avg_cost:.2f}",
            f"{p.current_price:.2f}",
            f"¥{p.market_value:,.2f}",
            f"[{c}]¥{p.pnl:,.2f}[/{c}]",
            f"[{c}]{p.pnl_pct:+.2f}%[/{c}]",
        )

    console.print(table)
    console.print()


@report.command()
@click.option(
    "--file",
    "-f",
    "perf_file",
    type=click.Path(exists=True),
    default=None,
    help="Performance metrics JSON file.",
)
def performance(perf_file: str | None):
    """Display performance report.

    Without --file, aggregates from saved backtest results.
    """
    if perf_file:
        with open(perf_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        metrics = PerformanceMetrics(**raw)
    else:
        # Try to aggregate from backtest history
        bt_dir = Path.home() / ".trading-wisdom" / "backtest_results"
        results = []
        if bt_dir.exists():
            for fp in sorted(bt_dir.glob("*.json"), reverse=True)[:20]:
                with open(fp, "r") as f:
                    results.append(json.load(f))

        if not results:
            # Demo metrics
            metrics = PerformanceMetrics(
                period_start=date.today() - timedelta(days=90),
                period_end=date.today(),
                starting_equity=100000,
                ending_equity=108500,
                total_trades=42,
                winning_trades=25,
                losing_trades=17,
                total_pnl=8500,
                max_drawdown=5.2,
                sharpe_ratio=1.45,
                win_rate=59.5,
                best_trade_pnl=3200,
                worst_trade_pnl=-1800,
            )
        else:
            # Aggregate from backtest results
            total_trades = sum(r.get("total_trades", 0) for r in results)
            winning = sum(r.get("winning_trades", 0) for r in results)
            metrics = PerformanceMetrics(
                period_start=date.today() - timedelta(days=90),
                period_end=date.today(),
                starting_equity=results[-1].get("initial_capital", 100000),
                ending_equity=results[0].get("final_equity", 100000),
                total_trades=total_trades,
                winning_trades=winning,
                losing_trades=total_trades - winning,
                total_pnl=sum(r.get("total_pnl", 0) for r in results),
                max_drawdown=max(
                    (r.get("max_drawdown", 0) for r in results), default=0
                ),
                sharpe_ratio=results[0].get("sharpe_ratio", 0) if results else 0,
                win_rate=(winning / total_trades * 100) if total_trades else 0,
            )

    report_data = _generator.generate_performance_report(metrics)

    ret_color = "green" if metrics.return_pct >= 0 else "red"
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("k", style="dim", width=20)
    table.add_column("v", justify="right")

    table.add_row("Period", report_data["period"])
    table.add_row("Starting Equity", f"¥{metrics.starting_equity:,.2f}")
    table.add_row("Ending Equity", f"¥{metrics.ending_equity:,.2f}")
    table.add_row("Return", f"[{ret_color}]{metrics.return_pct:+.2f}%[/{ret_color}]")
    table.add_row("Total P&L", f"[{ret_color}]¥{metrics.total_pnl:,.2f}[/{ret_color}]")
    table.add_row("", "")
    table.add_row("Total Trades", f"{metrics.total_trades}")
    table.add_row("Win Rate", f"{metrics.win_rate:.1f}%")
    table.add_row("Best Trade", f"[green]¥{metrics.best_trade_pnl:,.2f}[/green]")
    table.add_row("Worst Trade", f"[red]¥{metrics.worst_trade_pnl:,.2f}[/red]")
    table.add_row("", "")
    table.add_row("Max Drawdown", f"[red]{metrics.max_drawdown:.2f}%[/red]")
    table.add_row("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}")

    console.print()
    console.print(
        Panel(table, title="[bold]Performance Report[/bold]", border_style="blue")
    )
    console.print()


@report.command()
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["json", "csv"]),
    default="json",
    help="Export format.",
)
@click.option(
    "--type",
    "-t",
    "report_type",
    type=click.Choice(["portfolio", "performance"]),
    default="portfolio",
)
def export(fmt: str, report_type: str):
    """Export report to file."""
    if report_type == "portfolio":
        summary = PortfolioSummary(
            cash=50000,
            positions=[
                PortfolioPosition(
                    symbol="000001.SZ",
                    quantity=1000,
                    avg_cost=10.50,
                    current_price=11.12,
                ),
            ],
        )
        data = _generator.generate_portfolio_report(summary)
    else:
        metrics = PerformanceMetrics(
            period_start=date.today() - timedelta(days=90),
            period_end=date.today(),
            starting_equity=100000,
            ending_equity=108500,
            total_trades=42,
            winning_trades=25,
            losing_trades=17,
            total_pnl=8500,
        )
        data = _generator.generate_performance_report(metrics)

    if fmt == "json":
        path = _generator.export_json(data)
    else:
        rows = data.get("positions", [data])
        path = _generator.export_csv(rows, f"report_{report_type}_{date.today()}.csv")

    console.print(f"[green]✓[/green] Report exported to [cyan]{path}[/cyan]")


@report.command("list")
def report_list():
    """List saved reports."""
    reports = _generator.list_reports()
    if not reports:
        console.print("[yellow]No saved reports.[/yellow]")
        return

    table = Table(title="Saved Reports")
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Modified")

    for p in reports[:20]:
        size = p.stat().st_size
        modified = date.fromtimestamp(p.stat().st_mtime)
        table.add_row(p.name, f"{size:,} B", str(modified))

    console.print(table)
