# trading-wisdom-cli — Project Context for Claude

## Project Overview
AI-powered trading CLI framework supporting A-shares (CN), Hong Kong stocks (HK), and US stocks (US) with options analysis.

**Entry point:** `trading-cli` (installed via `pip install -e .`)
**Main file:** `trading_cli/main.py`

---

## Development Phases

### Phase 1: MVP Framework ✅ (Week 1-3)
- CLI skeleton with 12 command groups registered in `main.py`
- Configuration system: `trading_cli/core/config.py` (YAML + env var override)
- `trading-cli --version` → 0.1.0
- `trading-cli config show/set/validate` functional

### Phase 2: Core Features ✅ (Week 4-7)
- 9 core command groups: data, analyze, strategy, backtest, monitor, report, trade, workflow, debug
- Strategy framework: MA Cross, RSI, MACD, Bollinger — `trading_cli/strategy/`
- Backtest engine with P&L, Sharpe, Drawdown — `trading_cli/backtest/engine.py`
- Paper trading + risk engine — `trading_cli/core/paper_trader.py`, `risk.py`
- Strategy optimizer: grid search + genetic — `trading_cli/strategy/optimizer.py`
- Workflow YAML pipelines — `trading_cli/commands/workflow_cmd.py`

### Phase 3: Options Support ✅ (Week 8-10)
- Black-Scholes pricing + full Greeks — `trading_cli/core/options.py`
- Options commands: chain, greeks, iv, payoff — `trading_cli/commands/options_cmd.py`
- 6 options strategies (Covered Call, Iron Condor, etc.) — `trading_cli/strategy/options_strategies.py`

### Phase 4: International Markets ✅ (Week 11-12)
- IB provider (sim mode, no real account needed) — `trading_cli/core/ib_provider.py`
- Multi-market: CN/HK/US metadata, sessions, FX rates — `trading_cli/core/market.py`
- Market commands: info, fx, compare — `trading_cli/commands/market_cmd.py`

### Phase 5: Live Trading ✅ (Week 13-14)
- `BaseTrader` ABC — `trading_cli/core/base_trader.py`
- `RealTrader` (IBKR via ib_insync, lazy connect) — `trading_cli/core/live_trader.py`
- `TradeLogger` (JSON Lines, account_id truncated to last-4) — `trading_cli/core/trade_logger.py`
- `--live` / `--yes` flags on all trade commands; emergency stop group
- 20 unit tests for live trader + security audit passed
- Install with live trading: `pip install trading-wisdom-cli[ib]`

### Phase 6: Release ✅ (Week 15-16)
- E2E integration tests (3 scenarios, 21 tests) — `tests/test_e2e_pipeline.py`
- Security audit report — `docs/security-audit-2026-04-06.md`
- Docker multi-stage build — `Dockerfile`, `docker-compose.yml`, `docs/docker-deployment.md`
- Full documentation — `README.md`, `INSTALL.md`, `QUICKSTART.md`, `CHANGELOG.md`
- `python -m build` produces `trading_wisdom_cli-1.0.0.tar.gz` + `.whl`

---

## Current Stats
- **202 tests**, all passing (`python -m pytest tests/ -q`)
- **12 command groups**, 30+ CLI subcommands
- **39 source files**, black + mypy clean
- **Version:** 1.0.0 (`trading-cli --version`)

## Code Quality
- Formatter: `black` (run: `python -m black trading_cli/`)
- Type checker: `mypy trading_cli/ --ignore-missing-imports`
- Tests: `pytest tests/`
- Install: `pip install -e .`
- Dev deps: `pip install black mypy types-PyYAML pytest pytest-cov`

## Key Design Decisions
- Data providers: Tushare (CN), IB (HK/US, simulation supported)
- Backtest: custom engine in `trading_cli/backtest/engine.py`
- Live trading: IBKR via ib_insync (`pip install .[ib]`); CN A-shares raise NotImplementedError
- Config file: `~/.trading-cli/config.yaml` (auto-created with defaults)
- All float comparisons in tests must use `pytest.approx`

## Branch Strategy
- Develop directly on `main`; one commit per logical step
