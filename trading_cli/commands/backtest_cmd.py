"""Backtest commands."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

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
@click.option(
    "--capital", type=float, default=100000, help="Initial capital (default: 100,000)"
)
@click.option(
    "--days", "-d", type=int, default=365, help="Backtest period in days (default: 365)"
)
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
    console.print(f"Capital: [yellow]¥{capital:,.2f}[/yellow]\n")

    strategy = _get_strategy(strategy_name, params)
    if not strategy:
        console.print(f"[red]Strategy '{strategy_name}' not found.[/red]")
        return

    with console.status(f"[cyan]Fetching {symbol} data..."):
        df = _fetch_data(symbol, days)

    if df is None or df.empty:
        console.print(f"[red]No data available for {symbol}.[/red]")
        return

    console.print(f"[green]✓[/green] Loaded {len(df)} bars of data\n")

    with console.status("[cyan]Running backtest..."):
        engine = BacktestEngine(
            initial_capital=capital,
            commission_rate=strategy.config.commission_rate,
            slippage=strategy.config.slippage,
        )
        result = engine.run(strategy, df, symbol)

    _display_results(result)
    _save_result(result)


def _get_strategy(name: str, params: Optional[str] = None) -> Optional[Any]:
    """Get strategy instance by name."""
    if name in BUILTIN_STRATEGIES:
        cls = BUILTIN_STRATEGIES[name]
        strategy_params: dict[str, Any] = {}
        if params:
            import yaml

            strategy_params = yaml.safe_load(params) or {}

        config = StrategyConfig(
            name=name,
            description=cls.__doc__ or f"Built-in {name} strategy",
        )
        return cls(config, **strategy_params)

    reg = get_registry()
    strategy_config = reg.get(name)
    if strategy_config:
        return type(name, (), {"config": strategy_config})()

    return None


def _display_results(result):
    """Display backtest results."""
    content = Text()
    content.append("Total P&L: ", style="white")
    color = "green" if result.total_pnl >= 0 else "red"
    content.append(
        f"¥{result.total_pnl:+,.2f} ({result.total_pnl_pct:+.2f}%)\n", style=color
    )

    content.append("Total Trades: ", style="white")
    content.append(f"{result.total_trades}\n")

    content.append("Win Rate: ", style="white")
    wr_color = "green" if result.win_rate >= 50 else "yellow"
    content.append(f"{result.win_rate:.1f}%\n", style=wr_color)

    content.append("Max Drawdown: ", style="white")
    dd_color = "green" if abs(result.max_drawdown) < 10 else "red"
    content.append(f"{result.max_drawdown:.2f}%\n", style=dd_color)

    content.append("Sharpe Ratio: ", style="white")
    content.append(f"{result.sharpe_ratio:.2f}\n", style="yellow")

    content.append("Execution Time: ", style="white")
    content.append(f"{result.execution_time:.2f}s", style="cyan")

    panel = Panel(content, title="📊 Backtest Results", border_style="cyan")
    console.print(panel)

    if result.total_trades > 0:
        console.print("\n[cyan]Trade Breakdown:[/cyan]")
        table = Table(show_lines=False)
        table.add_column("Metric", style="white")
        table.add_column("Value", justify="right", style="green")
        table.add_row("Winning Trades", str(result.winning_trades))
        table.add_row("Losing Trades", str(result.losing_trades))
        table.add_row(
            "Avg P&L/Trade", f"¥{result.total_pnl / result.total_trades:,.2f}"
        )
        console.print(table)


def _save_result(result):
    """Save backtest result to file."""
    import json
    from pathlib import Path
    from datetime import datetime

    results_dir = Path.home() / ".trading-wisdom" / "backtest_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{result.strategy_name}_{result.symbol}_{timestamp}.json"
    path = results_dir / filename

    data = result.model_dump()
    data["start_date"] = str(data.get("start_date", ""))
    data["end_date"] = str(data.get("end_date", ""))

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    console.print(f"\n[dim]Results saved to {path}[/dim]")


@backtest.command()
@click.argument("symbol")
@click.option("--capital", type=float, default=100000, help="Initial capital")
@click.option("--days", "-d", type=int, default=365, help="Period in days")
@click.option(
    "--sort",
    "-s",
    type=click.Choice(["pnl", "sharpe", "win_rate", "drawdown"]),
    default="sharpe",
    help="Sort metric (default: sharpe)",
)
def compare(symbol: str, capital: float, days: int, sort: str):
    """Compare all built-in strategies on a symbol.

    Examples:

        trading-cli backtest compare 000001.SZ

        trading-cli backtest compare 600519 --sort pnl --days 180
    """
    console.print(f"\n[cyan]🔄 Comparing Strategies on {symbol}[/cyan]\n")

    with console.status(f"[cyan]Fetching {symbol} data..."):
        df = _fetch_data(symbol, days)

    if df is None or df.empty:
        console.print(f"[red]No data available for {symbol}.[/red]")
        return

    console.print(
        f"[green]✓[/green] Loaded {len(df)} bars | Period: {days} days | Capital: ¥{capital:,.0f}\n"
    )

    results = []
    for name, cls in BUILTIN_STRATEGIES.items():
        with console.status(f"[cyan]Testing {name}..."):
            config = StrategyConfig(name=name)
            strategy = cls(config)
            engine = BacktestEngine(initial_capital=capital)
            result = engine.run(strategy, df, symbol)
            results.append(result)

    sort_keys = {
        "pnl": lambda r: r.total_pnl,
        "sharpe": lambda r: r.sharpe_ratio,
        "win_rate": lambda r: r.win_rate,
        "drawdown": lambda r: -abs(r.max_drawdown),
    }
    results.sort(key=sort_keys[sort], reverse=True)

    table = Table(title=f"Strategy Comparison — {symbol}", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Strategy", style="cyan bold")
    table.add_column("P&L", justify="right")
    table.add_column("P&L%", justify="right")
    table.add_column("Trades", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Max DD", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("Time", justify="right", style="dim")

    for i, r in enumerate(results, 1):
        pnl_c = "green" if r.total_pnl >= 0 else "red"
        wr_c = "green" if r.win_rate >= 50 else "yellow"
        dd_c = "green" if abs(r.max_drawdown) < 10 else "red"
        sh_c = (
            "green" if r.sharpe_ratio > 1 else "yellow" if r.sharpe_ratio > 0 else "red"
        )
        rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else str(i)
        table.add_row(
            rank,
            r.strategy_name,
            f"[{pnl_c}]¥{r.total_pnl:+,.0f}[/{pnl_c}]",
            f"[{pnl_c}]{r.total_pnl_pct:+.2f}%[/{pnl_c}]",
            str(r.total_trades),
            f"[{wr_c}]{r.win_rate:.1f}%[/{wr_c}]",
            f"[{dd_c}]{r.max_drawdown:.1f}%[/{dd_c}]",
            f"[{sh_c}]{r.sharpe_ratio:.2f}[/{sh_c}]",
            f"{r.execution_time:.1f}s",
        )

    console.print(table)
    console.print()


@backtest.command()
@click.argument("strategy_name")
@click.argument("symbol")
@click.option(
    "--method",
    "-m",
    type=click.Choice(["grid", "genetic"]),
    default="grid",
    help="Optimisation method (default: grid)",
)
@click.option(
    "--metric",
    type=click.Choice(["sharpe_ratio", "total_pnl", "win_rate", "max_drawdown"]),
    default="sharpe_ratio",
    help="Optimisation target (default: sharpe_ratio)",
)
@click.option("--capital", type=float, default=100000, help="Initial capital")
@click.option("--days", "-d", type=int, default=365, help="Period in days")
@click.option(
    "--generations",
    "-g",
    type=int,
    default=10,
    help="Generations for genetic (default: 10)",
)
@click.option(
    "--population", type=int, default=20, help="Population for genetic (default: 20)"
)
@click.option(
    "--top", "-n", type=int, default=10, help="Show top N results (default: 10)"
)
def optimize(
    strategy_name: str,
    symbol: str,
    method: str,
    metric: str,
    capital: float,
    days: int,
    generations: int,
    population: int,
    top: int,
):
    """Optimise strategy parameters via grid search or genetic algorithm.

    Examples:

        trading-cli backtest optimize ma_cross 000001.SZ

        trading-cli backtest optimize rsi 600519 --method genetic --metric total_pnl

        trading-cli backtest optimize bollinger 000001.SZ --days 180 --top 5
    """
    from trading_cli.strategy.optimizer import grid_search, genetic_optimize

    if strategy_name not in BUILTIN_STRATEGIES:
        console.print(
            f"[red]Strategy '{strategy_name}' not found. Available: {', '.join(BUILTIN_STRATEGIES)}[/red]"
        )
        return

    cls = BUILTIN_STRATEGIES[strategy_name]

    # Define parameter grids per strategy
    grids: dict[str, dict[str, list[Any]]] = {
        "ma_cross": {
            "fast_period": [5, 8, 10, 12, 15, 20],
            "slow_period": [20, 25, 30, 40, 50, 60],
        },
        "rsi": {
            "period": [7, 10, 14, 21],
            "oversold": [20, 25, 30, 35],
            "overbought": [65, 70, 75, 80],
        },
        "macd": {
            "fast": [8, 10, 12, 15],
            "slow": [20, 24, 26, 30],
            "signal": [7, 9, 11],
        },
        "bollinger": {"period": [10, 15, 20, 25, 30], "std_dev": [1.5, 2.0, 2.5, 3.0]},
    }

    ranges: dict[str, dict[str, tuple[float, float, float]]] = {
        "ma_cross": {"fast_period": (5, 25, 1), "slow_period": (20, 60, 5)},
        "rsi": {
            "period": (5, 25, 1),
            "oversold": (15, 40, 5),
            "overbought": (60, 85, 5),
        },
        "macd": {"fast": (6, 18, 2), "slow": (18, 36, 2), "signal": (5, 15, 2)},
        "bollinger": {"period": (10, 40, 5), "std_dev": (1.0, 3.5, 0.5)},
    }

    console.print(f"\n[cyan]🔬 Strategy Optimisation[/cyan]")
    console.print(
        f"Strategy: [green]{strategy_name}[/green] | Method: [yellow]{method}[/yellow] | Metric: [yellow]{metric}[/yellow]"
    )
    console.print(
        f"Symbol: [green]{symbol}[/green] | Period: {days} days | Capital: ¥{capital:,.0f}\n"
    )

    with console.status(f"[cyan]Fetching {symbol} data..."):
        df = _fetch_data(symbol, days)

    if df is None or df.empty:
        console.print(f"[red]No data available for {symbol}.[/red]")
        return

    console.print(f"[green]✓[/green] Loaded {len(df)} bars\n")

    if method == "grid":
        param_grid = grids[strategy_name]
        combos = 1
        for v in param_grid.values():
            combos *= len(v)
        console.print(f"[dim]Grid search: {combos} parameter combinations[/dim]\n")

        with console.status(f"[cyan]Running grid search ({combos} combos)..."):
            result = grid_search(
                cls,
                df,
                symbol,
                param_grid,
                metric=metric,
                initial_capital=capital,
            )
    else:
        param_range = ranges[strategy_name]
        console.print(
            f"[dim]Genetic: {population} individuals × {generations} generations[/dim]\n"
        )

        with console.status(f"[cyan]Running genetic optimisation..."):
            result = genetic_optimize(
                cls,
                df,
                symbol,
                param_range,
                metric=metric,
                initial_capital=capital,
                population_size=population,
                generations=generations,
            )

    # Display best params
    console.print(
        Panel(
            f"[bold green]Best Parameters[/bold green]\n\n"
            + "\n".join(
                f"  {k}: [cyan]{v}[/cyan]" for k, v in result.best_params.items()
            )
            + f"\n\n[dim]Score ({metric}): {result.best_score:.4f}[/dim]"
            + f"\n[dim]Total combinations evaluated: {result.total_combinations}[/dim]",
            title=f"🏆 {method.upper()} Result",
            border_style="green",
        )
    )

    # Best result details
    br = result.best_result
    console.print(
        f"\n  P&L: [{'green' if br.total_pnl >= 0 else 'red'}]¥{br.total_pnl:+,.2f} ({br.total_pnl_pct:+.2f}%)[/]"
    )
    console.print(
        f"  Trades: {br.total_trades} | Win Rate: {br.win_rate:.1f}% | Drawdown: {br.max_drawdown:.1f}% | Sharpe: {br.sharpe_ratio:.2f}"
    )

    # Top N results table
    if result.all_results:
        console.print(
            f"\n[cyan]Top {min(top, len(result.all_results))} Results:[/cyan]"
        )
        table = Table(show_lines=False)
        table.add_column("#", style="dim", width=3)

        param_keys = list(result.best_params.keys())
        for k in param_keys:
            table.add_column(k, justify="right", style="cyan")
        table.add_column("Score", justify="right", style="bold")
        table.add_column("P&L%", justify="right")
        table.add_column("Win%", justify="right")
        table.add_column("Sharpe", justify="right")
        table.add_column("DD%", justify="right")

        for i, entry in enumerate(result.all_results[:top], 1):
            row = [str(i)]
            for k in param_keys:
                row.append(str(entry.get(k, "")))
            row.append(f"{entry.get('score', 0):.4f}")
            pnl_pct = entry.get("pnl_pct", 0)
            row.append(f"[{'green' if pnl_pct >= 0 else 'red'}]{pnl_pct:+.2f}%[/]")
            row.append(f"{entry.get('win_rate', 0):.0f}%")
            row.append(f"{entry.get('sharpe', 0):.2f}")
            row.append(f"{entry.get('drawdown', 0):.1f}%")
            table.add_row(*row)

        console.print(table)

    console.print()


@backtest.command()
def history():
    """Show backtest history.

    Examples:

        trading-cli backtest history
    """
    import json
    from pathlib import Path

    results_dir = Path.home() / ".trading-wisdom" / "backtest_results"

    if not results_dir.exists():
        console.print("[yellow]No backtest history found.[/yellow]")
        return

    files = sorted(
        results_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
    )

    if not files:
        console.print("[yellow]No backtest results saved.[/yellow]")
        return

    table = Table(title="Backtest History", show_lines=True)
    table.add_column("Date", style="cyan")
    table.add_column("Strategy", style="green")
    table.add_column("Symbol", style="yellow")
    table.add_column("P&L", justify="right")

    for path in files[:20]:
        with open(path) as f:
            data = json.load(f)

        pnl = data.get("total_pnl", 0)
        pnl_color = "green" if pnl >= 0 else "red"

        parts = path.stem.rsplit("_", 2)
        date_str = f"{parts[-2]}_{parts[-1]}" if len(parts) >= 3 else path.stem
        try:
            from datetime import datetime

            date_str = datetime.strptime(date_str, "%Y%m%d_%H%M%S").strftime(
                "%Y-%m-%d %H:%M"
            )
        except Exception:
            pass

        table.add_row(
            date_str,
            data.get("strategy_name", "unknown"),
            data.get("symbol", "unknown"),
            f"[{pnl_color}]¥{pnl:+,.2f}[/{pnl_color}]",
        )

    console.print(table)
