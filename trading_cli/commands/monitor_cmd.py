"""Real-time monitoring commands."""

from __future__ import annotations

from datetime import date, timedelta

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, Market, registry
from trading_cli.core.tushare_provider import TushareProvider
from trading_cli.core.monitor import AlertCondition, AlertManager, MarketSnapshot
from trading_cli.core.indicators import TechnicalIndicators

console = Console()

# Session-level alert manager
_alert_manager = AlertManager()


def _ensure_providers() -> None:
    if not registry.list_providers():
        config = get_config()
        registry.register(TushareProvider(config.data.tushare))


def _fetch_latest(symbol: str, days: int = 60) -> MarketSnapshot | None:
    """Fetch latest market snapshot for a symbol."""
    _ensure_providers()
    config = get_config()
    dp = registry.get(config.data.default_provider)
    request = DataFetchRequest(
        symbol=symbol,
        start_date=date.today() - timedelta(days=days),
        end_date=date.today(),
    )
    result = dp.fetch_stock_daily(request)
    if result.is_empty or len(result.data) < 2:
        return None
    last_row = result.data.iloc[-1]
    prev_close = float(result.data.iloc[-2]["close"])
    return MarketSnapshot.from_dataframe_row(symbol, last_row, prev_close)


@click.group()
def monitor():
    """👁️  Real-time Monitoring — dashboards, alerts, and market watch."""
    pass


@monitor.command()
@click.argument("symbols", nargs=-1, required=True)
def dashboard(symbols: tuple[str, ...]):
    """Display market dashboard for one or more symbols.

    Examples:

        trading-cli monitor dashboard 000001.SZ 600519.SH

        trading-cli monitor dashboard 000001.SZ
    """
    panels = []
    for sym in symbols:
        with console.status(f"Fetching {sym}..."):
            snap = _fetch_latest(sym)

        if snap is None:
            panels.append(Panel(f"[red]No data for {sym}[/red]", title=sym))
            continue

        color = "green" if snap.change_pct >= 0 else "red"
        content = Table(show_header=False, box=None, padding=(0, 1))
        content.add_column("label", style="dim", width=12)
        content.add_column("value", justify="right")

        content.add_row("Price", f"[bold {color}]{snap.close:.2f}[/bold {color}]")
        content.add_row("Change", f"[{color}]{snap.change_pct:+.2f}%[/{color}]")
        content.add_row("Open", f"{snap.open:.2f}")
        content.add_row("High", f"{snap.high:.2f}")
        content.add_row("Low", f"{snap.low:.2f}")
        content.add_row("Volume", f"{snap.vol:,.0f}")

        border_color = "green" if snap.change_pct >= 0 else "red"
        panels.append(
            Panel(content, title=f"[bold]{sym}[/bold]", border_style=border_color)
        )

    console.print()
    console.print(Columns(panels, equal=True, expand=True))
    console.print()


@monitor.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option(
    "--days", "-d", type=int, default=60, help="Lookback days for indicators."
)
def watch(symbols: tuple[str, ...], days: int):
    """Watch multiple symbols with key indicators.

    Examples:

        trading-cli monitor watch 000001.SZ 600519.SH 000858.SZ
    """
    _ensure_providers()
    config = get_config()
    dp = registry.get(config.data.default_provider)

    table = Table(title="Market Watch", show_lines=True)
    table.add_column("Symbol", style="cyan bold")
    table.add_column("Price", justify="right")
    table.add_column("Chg%", justify="right")
    table.add_column("RSI(14)", justify="right")
    table.add_column("MA5", justify="right")
    table.add_column("MA20", justify="right")
    table.add_column("Vol", justify="right")
    table.add_column("Signal", justify="center")

    for sym in symbols:
        with console.status(f"Fetching {sym}..."):
            request = DataFetchRequest(
                symbol=sym,
                start_date=date.today() - timedelta(days=days),
                end_date=date.today(),
            )
            try:
                result = dp.fetch_stock_daily(request)
            except Exception:
                table.add_row(sym, "[red]Error[/red]", "-", "-", "-", "-", "-", "-")
                continue

        if result.is_empty or len(result.data) < 20:
            table.add_row(sym, "[yellow]N/A[/yellow]", "-", "-", "-", "-", "-", "-")
            continue

        df = result.data
        last = df.iloc[-1]
        prev_close = (
            float(df.iloc[-2]["close"]) if len(df) > 1 else float(last["close"])
        )
        close = float(last["close"])
        change_pct = (close - prev_close) / prev_close * 100

        rsi_series = TechnicalIndicators.rsi(df)
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 0
        ma5 = float(df["close"].rolling(5).mean().iloc[-1])
        ma20 = float(df["close"].rolling(20).mean().iloc[-1])
        vol = float(last["vol"])

        # Simple signal
        if rsi < 30:
            signal = "[green bold]BUY[/green bold]"
        elif rsi > 70:
            signal = "[red bold]SELL[/red bold]"
        elif close > ma20:
            signal = "[green]Bullish[/green]"
        elif close < ma20:
            signal = "[red]Bearish[/red]"
        else:
            signal = "[yellow]HOLD[/yellow]"

        color = "green" if change_pct >= 0 else "red"
        table.add_row(
            sym,
            f"{close:.2f}",
            f"[{color}]{change_pct:+.2f}%[/{color}]",
            f"{rsi:.1f}",
            f"{ma5:.2f}",
            f"{ma20:.2f}",
            f"{vol:,.0f}",
            signal,
        )

    console.print()
    console.print(table)
    console.print()


@monitor.group()
def alert():
    """Manage price alerts."""
    pass


@alert.command("add")
@click.argument("symbol")
@click.option(
    "--condition",
    "-c",
    type=click.Choice([c.value for c in AlertCondition], case_sensitive=False),
    required=True,
    help="Alert condition type.",
)
@click.option("--threshold", "-t", type=float, required=True, help="Threshold value.")
@click.option("--message", "-m", default="", help="Custom alert message.")
def alert_add(symbol: str, condition: str, threshold: float, message: str):
    """Add a new alert rule.

    Examples:

        trading-cli monitor alert add 000001.SZ -c price_above -t 12.0

        trading-cli monitor alert add 600519.SH -c rsi_below -t 30
    """
    rule = _alert_manager.add_rule(
        symbol, AlertCondition(condition), threshold, message
    )
    console.print(
        f"[green]✓[/green] Alert created: [cyan]{rule.id}[/cyan] — {rule.message}"
    )


@alert.command("list")
@click.option("--symbol", "-s", default=None, help="Filter by symbol.")
def alert_list(symbol: str | None):
    """List active alert rules."""
    rules = _alert_manager.list_rules(symbol)
    if not rules:
        console.print("[yellow]No alert rules configured.[/yellow]")
        return

    table = Table(title="Alert Rules")
    table.add_column("ID", style="cyan")
    table.add_column("Symbol", style="bold")
    table.add_column("Condition")
    table.add_column("Threshold", justify="right")
    table.add_column("Status")

    for r in rules:
        status = "[red]TRIGGERED[/red]" if r.triggered else "[green]Active[/green]"
        table.add_row(r.id, r.symbol, r.condition.value, f"{r.threshold:.2f}", status)

    console.print(table)


@alert.command("remove")
@click.argument("rule_id")
def alert_remove(rule_id: str):
    """Remove an alert rule by ID."""
    if _alert_manager.remove_rule(rule_id):
        console.print(f"[green]✓[/green] Removed alert [cyan]{rule_id}[/cyan]")
    else:
        console.print(f"[red]Error:[/red] Alert '{rule_id}' not found.")


@alert.command("check")
@click.argument("symbols", nargs=-1, required=True)
def alert_check(symbols: tuple[str, ...]):
    """Check alerts against current market data.

    Examples:

        trading-cli monitor alert check 000001.SZ 600519.SH
    """
    rules = _alert_manager.list_rules()
    if not rules:
        console.print("[yellow]No alert rules to check.[/yellow]")
        return

    for sym in symbols:
        snap = _fetch_latest(sym)
        if snap is None:
            console.print(f"[yellow]⚠ No data for {sym}[/yellow]")
            continue

        market_data = {
            "close": snap.close,
            "change_pct": snap.change_pct,
            "vol": snap.vol,
        }
        triggered = _alert_manager.check_all(sym, market_data)
        if triggered:
            for rule in triggered:
                console.print(
                    f"[red bold]🔔 ALERT:[/red bold] {rule.message} (current: {market_data.get('close', 'N/A')})"
                )
        else:
            console.print(f"[dim]{sym}: no alerts triggered[/dim]")
