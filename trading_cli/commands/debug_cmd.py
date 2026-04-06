"""Debug and diagnostic tools."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from trading_cli.core.config import get_config, DEFAULT_CONFIG_FILE
from trading_cli.core.data_source import registry
from trading_cli.core.tushare_provider import TushareProvider

console = Console()


@click.group()
def debug():
    """🐛 Debug Tools — diagnostics, connectivity, and system info."""
    pass


@debug.command()
def connectivity():
    """Check connectivity to all configured data sources."""
    if not registry.list_providers():
        config = get_config()
        registry.register(TushareProvider(config.data.tushare))

    table = Table(title="Connectivity Check")
    table.add_column("Service", style="cyan")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    # Data providers
    for name in registry.list_providers():
        dp = registry.get(name)
        connected = dp.check_connection()
        status = "[green]✓ OK[/green]" if connected else "[red]✗ Failed[/red]"
        markets = ", ".join(m.value for m in dp.supported_markets)
        table.add_row(f"Data: {name}", status, f"Markets: {markets}")

    # Config file
    cfg_exists = DEFAULT_CONFIG_FILE.exists()
    table.add_row(
        "Config file",
        "[green]✓ Exists[/green]" if cfg_exists else "[yellow]⚠ Not found[/yellow]",
        str(DEFAULT_CONFIG_FILE),
    )

    # Tushare token
    config = get_config()
    has_token = bool(config.data.tushare.token)
    table.add_row(
        "Tushare token",
        "[green]✓ Set[/green]" if has_token else "[red]✗ Missing[/red]",
        (
            f"{config.data.tushare.token[:8]}..."
            if has_token
            else "Run: config set data.tushare.token <TOKEN>"
        ),
    )

    console.print()
    console.print(table)
    console.print()


@debug.command()
def info():
    """Show system and project info."""
    import sys
    import platform

    table = Table(title="System Info", show_header=False)
    table.add_column("key", style="dim", width=20)
    table.add_column("value")

    table.add_row("Python", sys.version.split()[0])
    table.add_row("Platform", platform.platform())
    from trading_cli import __version__
    table.add_row("CLI Version", __version__)
    table.add_row("Config Path", str(DEFAULT_CONFIG_FILE))

    # Directories
    dirs = {
        "Strategies": Path.home() / ".trading-wisdom" / "strategies",
        "Backtest Results": Path.home() / ".trading-wisdom" / "backtest_results",
        "Reports": Path.home() / ".trading-wisdom" / "reports",
        "Workflows": Path.home() / ".trading-wisdom" / "workflows",
    }
    for name, path in dirs.items():
        exists = path.exists()
        count = len(list(path.iterdir())) if exists else 0
        table.add_row(
            name,
            f"{path} ({count} files)" if exists else f"{path} [dim](not created)[/dim]",
        )

    # Dependencies
    deps = ["click", "rich", "pandas", "numpy", "pydantic", "yaml", "requests"]
    for dep in deps:
        try:
            mod = __import__(dep)
            ver = getattr(mod, "__version__", "installed")
            table.add_row(f"  {dep}", f"[green]{ver}[/green]")
        except ImportError:
            table.add_row(f"  {dep}", "[red]not installed[/red]")

    console.print()
    console.print(table)
    console.print()


@debug.command()
@click.argument("symbol")
def data_check(symbol: str):
    """Diagnose data fetch issues for a symbol."""
    from datetime import date, timedelta
    from trading_cli.core.data_source import DataFetchRequest

    console.print(f"\n[cyan]🔍 Data diagnostics for {symbol}[/cyan]\n")

    # Step 1: Config
    config = get_config()
    has_token = bool(config.data.tushare.token)
    console.print(
        f"  1. Token configured: {'[green]✓[/green]' if has_token else '[red]✗[/red]'}"
    )
    if not has_token:
        console.print(
            "     [red]Fix: trading-cli config set data.tushare.token YOUR_TOKEN[/red]"
        )
        return

    # Step 2: Provider
    if not registry.list_providers():
        registry.register(TushareProvider(config.data.tushare))
    dp = registry.get(config.data.default_provider)
    connected = dp.check_connection()
    console.print(
        f"  2. Provider connected: {'[green]✓[/green]' if connected else '[red]✗[/red]'}"
    )

    # Step 3: Data fetch
    request = DataFetchRequest(
        symbol=symbol,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(),
    )
    try:
        result = dp.fetch_stock_daily(request)
        console.print(f"  3. Data fetch: [green]✓ {result.row_count} rows[/green]")
        if not result.is_empty:
            df = result.data
            console.print(
                f"     Date range: {df['trade_date'].iloc[0].date()} → {df['trade_date'].iloc[-1].date()}"
            )
            console.print(f"     Columns: {', '.join(df.columns)}")
            console.print(f"     Last close: ¥{df['close'].iloc[-1]:.2f}")
        else:
            console.print(
                "     [yellow]⚠ Empty result — symbol may be invalid or delisted[/yellow]"
            )
    except Exception as e:
        console.print(f"  3. Data fetch: [red]✗ {e}[/red]")

    console.print()
