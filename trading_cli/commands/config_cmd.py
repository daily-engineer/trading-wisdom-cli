"""Configuration management commands."""

from __future__ import annotations

from typing import Any

import click
from rich.console import Console
from rich.syntax import Syntax
import yaml

from trading_cli.core.config import AppConfig, DEFAULT_CONFIG_FILE, get_config

console = Console()


@click.group()
def config():
    """⚙️  Configuration — manage CLI settings."""
    pass


@config.command()
def show():
    """Show current configuration."""
    cfg = get_config()
    yaml_str = yaml.dump(
        cfg.model_dump(),
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    console.print(f"\n[dim]Config file: {DEFAULT_CONFIG_FILE}[/dim]\n")
    syntax = Syntax(yaml_str, "yaml", theme="monokai", line_numbers=False)
    console.print(syntax)


@config.command()
@click.argument("key")
@click.argument("value")
def set(key: str, value: str):
    """Set a configuration value.

    KEY uses dot notation: data.tushare.token, log_level, etc.

    Examples:

        trading-cli config set data.tushare.token YOUR_TOKEN

        trading-cli config set log_level DEBUG
    """
    cfg = get_config()
    data = cfg.model_dump()

    # Navigate dot-separated key
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            console.print(f"[red]Error:[/red] Invalid config key: {key}")
            raise SystemExit(1)
        target = target[part]

    last_key = parts[-1]
    if last_key not in target:
        console.print(f"[red]Error:[/red] Unknown config key: {key}")
        raise SystemExit(1)

    # Type coercion
    old_value = target[last_key]
    coerced_value: Any
    if isinstance(old_value, bool):
        coerced_value = value.lower() in ("true", "1", "yes")
    elif isinstance(old_value, int):
        coerced_value = int(value)
    else:
        coerced_value = value

    target[last_key] = coerced_value

    new_cfg = AppConfig.model_validate(data)
    saved_path = new_cfg.save()
    console.print(
        f"[green]✓[/green] Set [cyan]{key}[/cyan] = [yellow]{coerced_value}[/yellow]"
    )
    console.print(f"[dim]Saved to {saved_path}[/dim]")


@config.command()
def init():
    """Initialize default configuration file."""
    if DEFAULT_CONFIG_FILE.exists():
        if not click.confirm(
            f"Config file already exists at {DEFAULT_CONFIG_FILE}. Overwrite?"
        ):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    cfg = AppConfig()
    saved_path = cfg.save()
    console.print(
        f"[green]✓[/green] Default config created at [cyan]{saved_path}[/cyan]"
    )
    console.print(
        "[dim]Edit this file or use 'trading-cli config set' to configure.[/dim]"
    )


@config.command()
def path():
    """Show config file path."""
    exists = DEFAULT_CONFIG_FILE.exists()
    status = "[green]exists[/green]" if exists else "[yellow]not created yet[/yellow]"
    console.print(f"Config path: [cyan]{DEFAULT_CONFIG_FILE}[/cyan] ({status})")
