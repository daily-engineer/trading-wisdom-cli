"""Backtest commands."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import click
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, Market, registry
from trading_cli.core.tushare_provider import TushareProvider
from trading_cli.backtest import BacktestEngine
from trading_cli.strategy.registry import get_registry
from trading_cli.strategy.builtin import BUILTIN_STRATEGIES
from trading_cli.strategy.models import StrategyConfig

console = Console()


def _ensure_provider():
    """Ensure data provider is registered."""
    if not registry.list_providers():
        config = get_config()
        provider = TushareProvider(config.data.tushare)
        registry.register(provider)


def _fetch_data(symbol: str, days: int = 365) -> Optional[pd.DataFrame]:
    """Fetch stock data for backtesting."""
    _ensure_provider()
    config = get_config()
    dp = registry.get(config.data.default_provider)
    
    request = DataFetchRequest(
        symbol=symbol,
        start_date=date.today() - timedelta(days=days),
        end_date=date.today(),
        market=Market.CN,
    )
    
    try:
        result = dp.fetch_stock_daily(request)
        return result.data
    except Exception as e:
        console.print(f"[red]Failed to fetch data: {e}[/red]")
        return None


@click.group()
def backtest():
    """🔄 Backtest — run strategy backtests on historical data."""
    pass


@backtest.command()
@click.argument("strategy_name")
@click.argument("symbol")
@click.option("--capital", type=float, default=100000, help="Initial capital (default: 100,000)")
@click.option("--days", "-d", type=int, default=365, help="Backtest period in days (default: 365)")
@click.option("--params", "-p", help="Strategy parameters as JSON string")
def run(strategy_name: str, symbol: str, capital: float, days: int, params: str | None):
    """Run a strategy backtest.
    
    Examples:
    
        trading-cli backtest run ma_cross 000001.SZ
        
        trading-cli backtest run rsi 600519 --capital 50000 --days 180
        
        trading-cli backtest run bollinger 000001.SZ --params '{"period": 30}'
    """
    console.print(f"\n[cyan]🔄 Running Backtest[/cyan]")
    console.print(f"Strategy: [green]{strategy_name}[/green]")
    console.print(f"Symbol: [green]{symbol}[/green]")
    console.print(f"Period: [yellow]{days} days[/yellow]")
    console.print(f"Capital: [yellow]${capital:,.2f}[/yellow]\n")
    
    # Get strategy
    strategy = _get_strategy(strategy_name, params)
    if not strategy:
        console.print(f"[red]Strategy '{strategy_name}' not found.[/red]")
        return
    
    # Fetch data
    with console.status(f"[cyan]Fetching {symbol} data..."):
        df = _fetch_data(symbol, days)
    
    if df is None or df.empty:
        console.print(f"[red]No data available for {symbol}.[/red]")
        return
    
    console.print(f"[green]✓[/green] Loaded {len(df)} bars of data\n")
    
    # Run backtest
    with console.status("[cyan]Running backtest..."):
        engine = BacktestEngine(
            initial_capital=capital,
            commission_rate=strategy.config.commission_rate,
            slippage=strategy.config.slippage
        )
        result = engine.run(strategy, df, symbol)
    
    # Display results
    _display_results(result)
    
    # Save result
    _save_result(result)


def _get_strategy(name: str, params: str = None) -> Optional:
    """Get strategy instance by name."""
    # Built-in strategies
    if name in BUILTIN_STRATEGIES:
        cls = BUILTIN_STRATEGIES[name]
        strategy_params = {}
        if params:
            import yaml
            strategy_params = yaml.safe_load(params) or {}
        
        config = StrategyConfig(
            name=name,
            description=cls.__doc__ or f"Built-in {name} strategy"
        )
        return cls(config, **strategy_params)
    
    # Custom strategies
    reg = get_registry()
    config = reg.get(name)
    if config:
        return type(name, (), {"config": config})()
    
    return None


def _display_results(result):
    """Display backtest results."""
    # Summary panel
    content = Text()
    content.append(f"Total P&L: ", style="white")
    color = "green" if result.total_pnl >= 0 else "red"
    content.append(f"${result.total_pnl:+,.2f} ({result.total_pnl_pct:+.2f}%)\n", style=color)
    
    content.append(f"Total Trades: ", style="white")
    content.append(f"{result.total_trades}\n")
    
    content.append(f"Win Rate: ", style="white")
    wr_color = "green" if result.win_rate >= 50 else "yellow"
    content.append(f"{result.win_rate:.1f}%\n", style=wr_color)
    
    content.append(f"Max Drawdown: ", style="white")
    dd_color = "green" if abs(result.max_drawdown) < 10 else "red"
    content.append(f"{result.max_drawdown:.2f}%\n", style=dd_color)
    
    content.append(f"Sharpe Ratio: ", style="white")
    content.append(f"{result.sharpe_ratio:.2f}\n", style="yellow")
    
    content.append(f"Execution Time: ", style="white")
    content.append(f"{result.execution_time:.2f}s", style="cyan")
    
    panel = Panel(
        content,
        title="📊 Backtest Results",
        border_style="cyan"
    )
    console.print(panel)
    
    # Trade breakdown
    if result.total_trades > 0:
        console.print("\n[cyan]Trade Breakdown:[/cyan]")
        table = Table(show_lines=False)
        table.add_column("Metric", style="white")
        table.add_column("Value", justify="right", style="green")
        
        table.add_row("Winning Trades", str(result.winning_trades))
        table.add_row("Losing Trades", str(result.losing_trades))
        table.add_row("Avg Win", f"${result.total_pnl / result.total_trades:,.2f}" if result.total_trades > 0 else "N/A")
        
        console.print(table)


def _save_result(result):
    """Save backtest result to file."""
    import json
    from pathlib import Path
    from datetime import datetime
    
    # Create results directory
    results_dir = Path.home() / ".trading-wisdom" / "backtest_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{result.strategy_name}_{result.symbol}_{timestamp}.json"
    path = results_dir / filename
    
    # Save
    data = result.model_dump()
    # Convert datetime and DataFrame to strings
    data["start_date"] = str(data.get("start_date", ""))
    data["end_date"] = str(data.get("end_date", ""))
    
    with open(path) as f:
        json.dump(data, f, indent=2, default=str)
    
    console.print(f"\n[dim]Results saved to {path}[/dim]")


@backtest.command()
@click.argument("symbol")
@click.option("--capital", type=float, default=100000, help="Initial capital")
@click.option("--days", "-d", type=int, default=365, help="Period in days")
def compare(symbol: str, capital: float, days: int):
    """Compare all built-in strategies on a symbol.
    
    Examples:
    
        trading-cli backtest compare 000001.SZ
    """
    console.print(f"\n[cyan]🔄 Comparing Strategies on {symbol}[/cyan]\n")
    
    # Fetch data
    with console.status(f"[cyan]Fetching {symbol} data..."):
        df = _fetch_data(symbol, days)
    
    if df is None or df.empty:
        console.print(f"[red]No data available for {symbol}.[/red]")
        return
    
    console.print(f"[green]✓[/green] Loaded {len(df)} bars of data\n")
    
    # Run each strategy
    results = []
    
    for name, cls in BUILTIN_STRATEGIES.items():
        with console.status(f"[cyan]Testing {name}..."):
            config = StrategyConfig(name=name)
            strategy = cls(config)
            
            engine = BacktestEngine(initial_capital=capital)
            result = engine.run(strategy, df, symbol)
            results.append(result)
    
    # Display comparison
    console.print("[cyan]Strategy Comparison:[/cyan]")
    table = Table(show_lines=True)
    table.add_column("Strategy", style="green")
    table.add_column("P&L", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Sharpe", justify="right")
    
    for result in sorted(results, key=lambda x: x.total_pnl, reverse=True):
        pnl_color = "green" if result.total_pnl >= 0 else "red"
        table.add_row(
            result.strategy_name,
            f"[{pnn_color}]${result.total_pnl:+,.0f}[/{pnl_color}]",
            str(result.total_trades),
            f"{result.win_rate:.0f}%",
            f"{result.max_drawdown:.1f}%",
            f"{result.sharpe_ratio:.2f}"
        )
    
    console.print(table)


@backtest.command()
def history():
    """Show backtest history.
    
    Examples:
    
        trading-cli backtest history
    """
    from pathlib import Path
    
    results_dir = Path.home() / ".trading-wisdom" / "backtest_results"
    
    if not results_dir.exists():
        console.print("[yellow]No backtest history found.[/yellow]")
        return
    
    files = sorted(results_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not files:
        console.print("[yellow]No backtest results saved.[/yellow]")
        return
    
    table = Table(title="Backtest History", show_lines=True)
    table.add_column("Date", style="cyan")
    table.add_column("Strategy", style="green")
    table.add_column("Symbol", style="yellow")
    table.add_column("P&L", justify="right")
    
    for path in files[:20]:
        import json
        with open(path) as f:
            data = json.load(f)
        
        pnl = data.get("total_pnl", 0)
        pnl_color = "green" if pnl >= 0 else "red"
        
        # Extract date from filename
        date_str = path.stem.split("_")[-1]
        try:
            from datetime import datetime
            date_str = datetime.strptime(date_str, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M")
        except:
            pass
        
        table.add_row(
            date_str,
            data.get("strategy_name", "unknown"),
            data.get("symbol", "unknown"),
            f"[{pnl_color}]${pnl:+,.2f}[/{pnl_color}]"
        )
    
    console.print(table)
