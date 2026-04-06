"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner

from trading_cli.main import cli

runner = CliRunner()


def test_cli_help():
    """CLI --help should show all command groups."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "data" in result.output
    assert "config" in result.output
    assert "analyze" in result.output
    assert "strategy" in result.output


def test_cli_version():
    """CLI --version should show version."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_data_help():
    """data --help should show subcommands."""
    result = runner.invoke(cli, ["data", "--help"])
    assert result.exit_code == 0
    assert "fetch" in result.output
    assert "sources" in result.output
    assert "validate" in result.output


def test_config_help():
    """config --help should show subcommands."""
    result = runner.invoke(cli, ["config", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output
    assert "set" in result.output
    assert "init" in result.output
    assert "path" in result.output


def test_config_show():
    """config show should display configuration."""
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "tushare" in result.output
    assert "default_provider" in result.output


def test_config_path():
    """config path should display file path."""
    result = runner.invoke(cli, ["config", "path"])
    assert result.exit_code == 0
    assert "config.yaml" in result.output


def test_data_sources():
    """data sources should list providers."""
    result = runner.invoke(cli, ["data", "sources"])
    assert result.exit_code == 0
    assert "tushare" in result.output


@pytest.fixture
def cli_runner():
    return CliRunner()


def test_emergency_stop_paper(cli_runner):
    """Emergency stop in paper mode with empty account reports no positions."""
    result = cli_runner.invoke(cli, ["trade", "emergency", "stop"])
    assert result.exception is None
    assert result.exit_code == 0
    assert "No open positions to close" in result.output


def test_order_buy_live_requires_confirm(cli_runner):
    """--live flag without --yes should show warning and cancel on 'n'."""
    result = cli_runner.invoke(
        cli, ["trade", "order", "buy", "AAPL", "--qty", "1", "--live"], input="n\n"
    )
    assert result.exit_code == 0
    assert "LIVE ORDER" in result.output
    assert "Cancelled" in result.output


def test_order_sell_live_requires_confirm(cli_runner):
    """--live sell without --yes should show warning and cancel on 'n'."""
    result = cli_runner.invoke(
        cli,
        ["trade", "order", "sell", "AAPL", "--qty", "10", "--live"],
        input="n\n",
    )
    assert result.exit_code == 0
    assert "LIVE ORDER" in result.output
    assert "Cancelled" in result.output


def test_order_buy_live_yes_skips_confirm(cli_runner):
    """--live --yes should skip the confirmation prompt."""
    result = cli_runner.invoke(
        cli, ["trade", "order", "buy", "AAPL", "--qty", "1", "--live", "--yes"]
    )
    # Will fail to fetch price (no real data source in tests), but no confirmation prompt
    assert "Confirm?" not in result.output
