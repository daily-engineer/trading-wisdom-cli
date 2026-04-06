"""Data management commands."""

from __future__ import annotations

from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table

from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, Market, registry
from trading_cli.core.tushare_provider import TushareProvider

console = Console()


def _ensure_providers() -> None:
    """Register default data providers if not already registered."""
    if not registry.list_providers():
        config = get_config()
        tushare = TushareProvider(config.data.tushare)
        registry.register(tushare)


@click.group()
def data():
    """📊 Data Management — fetch, validate, and manage market data."""
    pass


@data.command()
@click.argument("symbol")
@click.option(
    "--market",
    "-m",
    type=click.Choice(["CN", "HK", "US"], case_sensitive=False),
    default="CN",
    help="Target market (default: CN).",
)
@click.option("--start", "-s", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Start date (YYYY-MM-DD).")
@click.option("--end", "-e", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="End date (YYYY-MM-DD).")
@click.option("--days", "-d", type=int, default=30, help="Number of recent days (default: 30).")
@click.option("--provider", "-p", default=None, help="Data provider name.")
@click.option("--limit", "-l", type=int, default=20, help="Max rows to display (default: 20).")
def fetch(symbol: str, market: str, start, end, days: int, provider: str | None, limit: int):
    """Fetch stock market data.

    Examples:

        trading-cli data fetch 000001.SZ

        trading-cli data fetch 600519 --days 60

        trading-cli data fetch AAPL --market US
    """
    _ensure_providers()

    config = get_config()
    provider_name = provider or config.data.default_provider
    try:
        dp = registry.get(provider_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    start_date = start.date() if start else date.today() - timedelta(days=days)
    end_date = end.date() if end else date.today()

    request = DataFetchRequest(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        market=Market(market.upper()),
    )

    with console.status(f"Fetching {symbol} from {provider_name}..."):
        try:
            result = dp.fetch_stock_daily(request)
        except Exception as e:
            console.print(f"[red]Fetch failed:[/red] {e}")
            raise SystemExit(1)

    if result.is_empty:
        console.print(f"[yellow]No data returned for {symbol}.[/yellow]")
        return

    console.print(
        f"\n[green]✓[/green] {result.symbol} | {result.provider} | "
        f"{result.row_count} rows | {result.market.value} market\n"
    )

    # Build Rich table
    table = Table(title=f"{result.symbol} Daily Data", show_lines=False)
    display_cols = ["trade_date", "open", "high", "low", "close", "vol"]
    for col in display_cols:
        if col in result.data.columns:
            table.add_column(col, justify="right" if col != "trade_date" else "left")

    df_display = result.data.tail(limit)
    for _, row in df_display.iterrows():
        values = []
        for col in display_cols:
            if col in result.data.columns:
                val = row[col]
                if col == "trade_date":
                    values.append(str(val.date()) if hasattr(val, "date") else str(val))
                elif col == "vol":
                    values.append(f"{val:,.0f}")
                else:
                    values.append(f"{val:.2f}")
        table.add_row(*values)

    console.print(table)


@data.command()
def sources():
    """List available data sources."""
    _ensure_providers()
    providers = registry.list_providers()
    if not providers:
        console.print("[yellow]No data providers configured.[/yellow]")
        return

    table = Table(title="Data Sources")
    table.add_column("Provider", style="cyan")
    table.add_column("Markets", style="green")
    table.add_column("Status", style="bold")

    for name in providers:
        dp = registry.get(name)
        markets = ", ".join(m.value for m in dp.supported_markets)
        connected = dp.check_connection()
        status = "[green]✓ Connected[/green]" if connected else "[red]✗ Not connected[/red]"
        table.add_row(name, markets, status)

    console.print(table)


@data.command()
@click.argument("symbol")
def validate(symbol: str):
    """Validate a stock symbol."""
    _ensure_providers()
    config = get_config()
    dp = registry.get(config.data.default_provider)

    with console.status(f"Validating {symbol}..."):
        request = DataFetchRequest(symbol=symbol)
        try:
            result = dp.fetch_stock_daily(request)
            if result.is_empty:
                console.print(f"[yellow]⚠ {symbol}: no data found (may be invalid).[/yellow]")
            else:
                console.print(f"[green]✓ {symbol}: valid ({result.row_count} records available).[/green]")
        except Exception as e:
            console.print(f"[red]✗ {symbol}: validation failed — {e}[/red]")
