# Changelog

All notable changes to Trading Wisdom CLI are documented here.

## [1.0.0] - 2026-04-06

### Added — Phase 5: Live Trading

- `BaseTrader` abstract base class (`trading_cli/core/base_trader.py`) defining the unified trader interface
- `RealTrader` via `ib_insync` for live Interactive Brokers execution (`trading_cli/core/live_trader.py`)
- `TradeLogger` JSON Lines audit log for all order activity (`trading_cli/core/trade_logger.py`)
- `--live` flag on `trade order buy`, `trade order sell`, `trade position close`, and `trade emergency stop`
- `--yes` flag to skip confirmation prompts in scripted live workflows
- `trade emergency stop` command — cancels all orders and closes all positions instantly
- `pip install trading-wisdom-cli[ib]` optional dependency group for `ib_insync`
- Dockerization: `Dockerfile`, `docker-compose.yml`, and `docs/docker-guide.md`
- End-to-end integration test suite (`tests/test_e2e_pipeline.py`)
- Security audit report (`docs/security-audit-2026-04-06.md`)

### Added — Phase 4: International Markets

- IB data provider with simulation mode (`trading_cli/core/ib_provider.py`)
- Multi-market metadata: CN/HK/US sessions, lot sizes, currency (`trading_cli/core/market.py`)
- FX rate lookups and cross-market comparison
- `market info`, `market fx`, `market compare` commands

### Added — Phase 3: Options Support

- Black-Scholes option pricing and full Greeks (delta, gamma, theta, vega, rho) (`trading_cli/core/options.py`)
- Option chain generation across configurable strikes
- 6 options strategies: Covered Call, Protective Put, Bull Call Spread, Bear Put Spread, Iron Condor, Straddle (`trading_cli/strategy/options_strategies.py`)
- `options chain`, `options greeks`, `options iv`, `options payoff` commands

### Added — Phase 2: Core Features

- Strategy framework with 4 built-in strategies: MA Cross, RSI, MACD, Bollinger Bands (`trading_cli/strategy/`)
- Backtest engine with P&L, Sharpe ratio, max drawdown, and win rate (`trading_cli/backtest/engine.py`)
- Strategy optimizer: grid search and genetic algorithm (`trading_cli/strategy/optimizer.py`)
- Paper trading engine with full order lifecycle (`trading_cli/core/paper_trader.py`)
- Risk engine: position size limits, stop loss, daily loss halt, cash reserve (`trading_cli/core/risk.py`)
- Workflow YAML pipeline runner (`trading_cli/commands/workflow_cmd.py`)
- `backtest run`, `backtest compare`, `backtest optimize` commands
- `trade order buy/sell/list/cancel`, `trade position list/close`, `trade account`, `trade risk` commands

## [0.1.0] - Initial Release

### Added — Phase 1: MVP Framework

- CLI entry point `trading-cli` via `pyproject.toml`
- 12 command group skeleton registered in `trading_cli/main.py`
- Configuration system: YAML file at `~/.trading-cli/config.yaml` with environment variable override (`trading_cli/core/config.py`)
- `config show`, `config set`, `config validate` commands
- `trading-cli --version` returns `0.1.0`
- Tushare data provider for A-shares (`trading_cli/core/tushare_provider.py`)
- `data fetch`, `data sources`, `data validate` commands
