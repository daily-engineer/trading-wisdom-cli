"""Tests for CLI commands."""

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
    assert "1.0.0" in result.output


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
