"""Tests for the configuration system."""

import yaml
import pytest

from trading_cli.core.config import AppConfig


def test_default_config():
    """Default config should have sensible defaults."""
    cfg = AppConfig()
    assert cfg.data.default_provider == "tushare"
    assert cfg.data.tushare.token == ""
    assert cfg.log_level == "INFO"
    assert cfg.output_format == "table"


def test_load_from_yaml(tmp_path):
    """Config should load from a YAML file."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump({
            "data": {"default_provider": "tushare", "tushare": {"token": "test123"}},
            "log_level": "DEBUG",
        })
    )
    cfg = AppConfig.load(config_file)
    assert cfg.data.tushare.token == "test123"
    assert cfg.log_level == "DEBUG"
    # Defaults still work for unspecified fields
    assert cfg.output_format == "table"


def test_load_missing_file(tmp_path):
    """Loading a missing file should return defaults."""
    cfg = AppConfig.load(tmp_path / "nonexistent.yaml")
    assert cfg.data.default_provider == "tushare"


def test_save_and_reload(tmp_path):
    """Config should round-trip through save/load."""
    cfg = AppConfig()
    cfg.data.tushare.token = "my_token"
    cfg.log_level = "WARNING"

    saved_path = cfg.save(tmp_path / "config.yaml")
    assert saved_path.exists()

    reloaded = AppConfig.load(saved_path)
    assert reloaded.data.tushare.token == "my_token"
    assert reloaded.log_level == "WARNING"


def test_load_empty_yaml(tmp_path):
    """An empty YAML file should return defaults."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    cfg = AppConfig.load(config_file)
    assert cfg.data.default_provider == "tushare"
