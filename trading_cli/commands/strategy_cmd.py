"""Strategy management commands."""

from __future__ import annotations

import click
import yaml
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from trading_cli.strategy.registry import get_registry
from trading_cli.strategy.builtin import BUILTIN_STRATEGIES

console = Console()


@click.group()
def strategy():
    """📈 Strategy Management — create, list, and manage trading strategies."""
    pass


@strategy.command()
@click.argument("name")
@click.option("--params", "-p", help="Strategy parameters as JSON string")
@click.option("--stop-loss", type=float, default=5.0, help="Stop loss percentage")
@click.option("--take-profit", type=float, default=10.0, help="Take profit percentage")
def create(name: str, params: str | None, stop_loss: float, take_prob: float):
    """Create a new strategy.
    
    Examples:
    
        trading-cli strategy create my_strategy
        
        trading-cli strategy create ma_cross --params '{"fast_period": 5, "slow_period": 20}'
    """
    registry = get_registry()
    
    # Check if built-in
    if name in BUILTIN_STRATEGIES:
        console.print(f"[yellow]'{name}' is a built-in strategy. Registering...[/yellow]")
        config = registry.register_builtin(name)
        console.print(f"[green]✓[/green] Built-in strategy '{name}' registered.")
        return
    
    # Check if already exists
    existing = registry.get(name)
    if existing:
        console.print(f"[yellow]Strategy '{name}' already exists.[/yellow]")
        return
    
    # Parse parameters
    strategy_params = {}
    if params:
        try:
            strategy_params = yaml.safe_load(params)
        except yaml.YAMLError as e:
            console.print(f"[red]Invalid JSON params: {e}[/red]")
            return
    
    from trading_cli.strategy.models import StrategyConfig
    
    config = StrategyConfig(
        name=name,
        description=f"Custom strategy: {name}",
        stop_loss_pct=stop_loss,
        take_profit_pct=take_prob
    )
    
    path = registry.save_to_yaml(config)
    console.print(f"[green]✓[/green] Strategy '{name}' created at {path}")


@strategy.command()
def list():
    """List all available strategies.
    
    Examples:
    
        trading-cli strategy list
    """
    registry = get_registry()
    registry.load_all()
    
    # Built-in strategies
    console.print("\n[cyan]Built-in Strategies:[/cyan]")
    if BUILTIN_STRATEGIES:
        table = Table(show_lines=False)
        table.add_column("Name", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Description")
        
        for name, cls in BUILTIN_STRATEGIES.items():
            table.add_row(
                name,
                cls.__name__,
                cls.__doc__ or ""
            )
        console.print(table)
    else:
        console.print("[yellow]No built-in strategies available.[/yellow]")
    
    # Custom strategies
    console.print("\n[cyan]Custom Strategies:[/cyan]")
    custom = registry.list()
    if custom:
        table = Table(show_lines=False)
        table.add_column("Name", style="green")
        table.add_column("Config", style="yellow")
        
        for name in custom:
            config = registry.get(name)
            table.add_row(name, f"SL:{config.stop_loss_pct}% TP:{config.take_profit_pct}%")
        console.print(table)
    else:
        console.print("[yellow]No custom strategies created yet.[/yellow]")


@strategy.command()
@click.argument("name")
def show(name: str):
    """Show strategy details.
    
    Examples:
    
        trading-cli strategy show ma_cross
    """
    registry = get_registry()
    
    # Check built-in first
    if name in BUILTIN_STRATEGIES:
        cls = BUILTIN_STRATEGIES[name]
        console.print(f"\n[green]Strategy:[/green] {name}")
        console.print(f"[yellow]Type:[/yellow] {cls.__name__}")
        console.print(f"[yellow]Description:[/yellow] {cls.__doc__ or 'N/A'}")
        
        from trading_cli.strategy.models import StrategyConfig
        config = StrategyConfig(name=name, description=cls.__doc__ or "")
        
        # Show default parameters
        if hasattr(cls, "__init__"):
            import inspect
            sig = inspect.signature(cls.__init__)
            console.print("\n[cyan]Default Parameters:[/cyan]")
            for param_name, param in sig.parameters.items():
                if param_name != "self" and param_name != "config":
                    default = param.default if param.default != inspect.Parameter.empty else "required"
                    console.print(f"  {param_name}: {default}")
        return
    
    # Check custom strategies
    config = registry.get(name)
    if not config:
        console.print(f"[red]Strategy '{name}' not found.[/red]")
        return
    
    console.print(f"\n[green]Strategy:[/green] {config.name}")
    console.print(f"[yellow]Description:[/yellow] {config.description}")
    console.print(f"[yellow]Enabled:[/yellow] {config.enabled}")
    console.print(f"[yellow]Stop Loss:[/yellow] {config.stop_loss_pct}%")
    console.print(f"[yellow]Take Profit:[/yellow] {config.take_profit_pct}%")
    console.print(f"[yellow]Position Size:[/yellow] {config.position_size * 100}%")
    console.print(f"[yellow]Commission Rate:[/yellow] {config.commission_rate * 100}%")


@strategy.command()
@click.argument("name")
def delete(name: str):
    """Delete a custom strategy.
    
    Examples:
    
        trading-cli strategy delete my_strategy
    """
    registry = get_registry()
    
    # Cannot delete built-in
    if name in BUILTIN_STRATEGIES:
        console.print(f"[red]Cannot delete built-in strategy '{name}'.[/red]")
        return
    
    if registry.remove(name):
        console.print(f"[green]✓[/green] Strategy '{name}' deleted.")
    else:
        console.print(f"[yellow]Strategy '{name}' not found.[/yellow]")
