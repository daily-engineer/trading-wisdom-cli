#!/usr/bin/env python3
"""
Trading Wisdom CLI - Main Entry Point

AI-powered trading framework supporting A-shares, Hong Kong stocks, US stocks, and options.
"""

import click

from trading_cli.commands.data_cmd import data
from trading_cli.commands.config_cmd import config
from trading_cli.commands.analyze_cmd import analyze
from trading_cli.commands.strategy_cmd import strategy
from trading_cli.commands.backtest_cmd import backtest
from trading_cli.commands.monitor_cmd import monitor
from trading_cli.commands.report_cmd import report
from trading_cli.commands.trade_cmd import trade
from trading_cli.commands.workflow_cmd import workflow
from trading_cli.commands.debug_cmd import debug
from trading_cli.commands.options_cmd import options
from trading_cli.commands.market_cmd import market
from trading_cli.commands.rps_cmd import rps
from trading_cli.commands.capital_flow_cmd import capital_flow
from trading_cli.commands.sentiment_cmd import sentiment


@click.group()
@click.version_option(version="1.0.0")
@click.pass_context
def cli(ctx):
    """
    Trading Wisdom CLI - AI-Powered Trading Framework

    A comprehensive command-line tool for intelligent trading analysis and execution.

    Supports: A-shares | Hong Kong stocks | US stocks | Options

    Examples:

        trading-cli data fetch 000001.SZ

        trading-cli trade order buy 000001.SZ --qty 1000

        trading-cli backtest optimize ma_cross 600519

    For more help on a specific command:

        trading-cli COMMAND --help
    """
    ctx.ensure_object(dict)


# All command groups — Phase 2 + Phase 3 (options)
cli.add_command(data)
cli.add_command(config)
cli.add_command(analyze)
cli.add_command(strategy)
cli.add_command(backtest)
cli.add_command(monitor)
cli.add_command(report)
cli.add_command(trade)
cli.add_command(workflow)
cli.add_command(debug)
cli.add_command(options)
cli.add_command(market)
cli.add_command(rps)
cli.add_command(capital_flow)
cli.add_command(sentiment)


if __name__ == "__main__":
    cli(obj={})
