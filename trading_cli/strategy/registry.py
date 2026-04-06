"""Strategy registry and management."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Optional

from trading_cli.strategy.models import StrategyConfig, Strategy
from trading_cli.strategy.builtin import BUILTIN_STRATEGIES


class StrategyRegistry:
    """Registry for managing trading strategies."""

    def __init__(self):
        self._strategies: dict[str, StrategyConfig] = {}
        self._strategy_dir = Path.home() / ".trading-wisdom" / "strategies"
        self._strategy_dir.mkdir(parents=True, exist_ok=True)

    def register_builtin(self, name: str) -> StrategyConfig:
        """Register a built-in strategy."""
        if name not in BUILTIN_STRATEGIES:
            raise ValueError(f"Unknown built-in strategy: {name}")

        if name in self._strategies:
            return self._strategies[name]

        config = StrategyConfig(name=name, description=f"Built-in {name} strategy")
        self._strategies[name] = config
        return config

    def create_from_yaml(self, yaml_path: str) -> StrategyConfig:
        """Create a strategy from YAML configuration."""
        path = Path(yaml_path)
        if not path.exists():
            # Try relative to strategy directory
            path = self._strategy_dir / yaml_path

        if not path.exists():
            raise FileNotFoundError(f"Strategy file not found: {yaml_path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        config = StrategyConfig(**data)
        self._strategies[config.name] = config
        self.save_to_yaml(config)

        return config

    def save_to_yaml(self, config: StrategyConfig) -> Path:
        """Save strategy config to YAML file."""
        path = self._strategy_dir / f"{config.name}.yaml"

        with open(path, "w") as f:
            yaml.dump(config.model_dump(), f, default_flow_style=False)

        return path

    def get(self, name: str) -> Optional[StrategyConfig]:
        """Get strategy by name."""
        return self._strategies.get(name)

    def list(self) -> list[str]:
        """List all registered strategies."""
        return list(self._strategies.keys())

    def remove(self, name: str) -> bool:
        """Remove a strategy."""
        if name in self._strategies:
            del self._strategies[name]
            # Also remove file if exists
            path = self._strategy_dir / f"{name}.yaml"
            if path.exists():
                path.unlink()
            return True
        return False

    def load_all(self):
        """Load all strategies from disk."""
        for path in self._strategy_dir.glob("*.yaml"):
            with open(path) as f:
                data = yaml.safe_load(f)
                config = StrategyConfig(**data)
                self._strategies[config.name] = config


# Global registry instance
_registry = StrategyRegistry()


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry."""
    return _registry
