#!/usr/bin/env python3
"""
Trading Wisdom CLI - Main Entry Point

AI-powered trading framework supporting A-shares, Hong Kong stocks, US stocks, and options.
"""

import click

from trading_cli.commands.data_cmd import data
from trading_cli.commands.config_cmd import config
from trading_cli.commands.analyze_cmd import analyze


@click.group()
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx):
    """
    Trading Wisdom CLI - AI-Powered Trading Framework

    A comprehensive command-line tool for intelligent trading analysis and execution.

    Supports: A-shares | Hong Kong stocks | US stocks | Options

    Examples:

        trading-cli data fetch 000001.SZ

        trading-cli data fetch 600519 --days 60

        trading-cli config show

    For more help on a specific command:

        trading-cli COMMAND --help
    """
    ctx.ensure_object(dict)


# Register implemented command groups
cli.add_command(data)
cli.add_command(config)
cli.add_command(analyze)


# Placeholder command groups (to be implemented in later phases)


@cli.group()
def strategy():
    """📈 Strategy Management (Phase 2)"""
    pass


@cli.group()
def trade():
    """💹 Trading Execution (Phase 2)"""
    pass


@cli.group()
def monitor():
    """👁️  Real-time Monitoring (Phase 2)"""
    pass


@cli.group()
def workflow():
    """🔄 Workflow Orchestration (Phase 2)"""
    pass


@cli.group()
def report():
    """📋 Reporting (Phase 2)"""
    pass


@cli.group()
def debug():
    """🐛 Debug Tools (Phase 2)"""
    pass


if __name__ == "__main__":
    cli(obj={})
