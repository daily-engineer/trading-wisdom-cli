"""Configuration system for Trading Wisdom CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

# Default config directory
DEFAULT_CONFIG_DIR = Path.home() / ".trading-cli"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"


class TushareConfig(BaseModel):
    """Tushare data source configuration."""

    token: str = ""
    api_url: str = "http://api.tushare.pro"


class DataSourceConfig(BaseModel):
    """Data source configuration."""

    default_provider: str = "tushare"
    tushare: TushareConfig = Field(default_factory=TushareConfig)
    cache_dir: str = ".cache/data"
    cache_ttl_hours: int = 24


class AnalyzeConfig(BaseModel):
    """Analysis configuration."""

    llm_provider: str = "openai"
    llm_model: str = "gpt-4"
    llm_api_key: str = ""


class AppConfig(BaseModel):
    """Root application configuration."""

    data: DataSourceConfig = Field(default_factory=DataSourceConfig)
    analyze: AnalyzeConfig = Field(default_factory=AnalyzeConfig)
    log_level: str = "INFO"
    output_format: str = "table"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> AppConfig:
        """Load config from YAML file, falling back to defaults."""
        config_path = path or DEFAULT_CONFIG_FILE
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            return cls.model_validate(raw)
        return cls()

    def save(self, path: Optional[Path] = None) -> Path:
        """Save current config to YAML file."""
        config_path = path or DEFAULT_CONFIG_FILE
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self.model_dump(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        return config_path


def get_config(path: Optional[Path] = None) -> AppConfig:
    """Get application configuration, writing defaults to disk on first run."""
    config_path = path or DEFAULT_CONFIG_FILE
    if not config_path.exists():
        cfg = AppConfig()
        cfg.save(config_path)
        return cfg
    return AppConfig.load(config_path)
