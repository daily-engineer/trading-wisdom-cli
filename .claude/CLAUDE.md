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

### Phase 5: Live Trading (Week 13-14) — NEXT
- Account management, live execution (vnpy/veighna)
- Security audit, emergency stop-loss, full integration tests

### Phase 6: Release (Week 15-16)
- Performance tuning, Docker, v1.0

---

## Current Stats
- **161 tests**, all passing (`python -m pytest tests/ -q`)
- **12 command groups**, 30+ CLI subcommands
- **36 source files**, black + mypy clean

## Code Quality
- Formatter: `black` (run: `python -m black trading_cli/`)
- Type checker: `mypy trading_cli/ --ignore-missing-imports`
- Tests: `pytest tests/`
- Install: `pip install -e .`
- Dev deps: `pip install black mypy types-PyYAML pytest pytest-cov`

## Key Design Decisions
- Data providers: Tushare (CN), IB (HK/US, simulation supported)
- Backtest: custom engine in `trading_cli/backtest/engine.py`; vectorbt/backtrader planned for Phase 5
- Live trading: vnpy (veighna) planned for Phase 5
- Config file: `~/.trading-cli/config.yaml` (auto-created with defaults)
- All float comparisons in tests must use `pytest.approx`

## Branch Strategy
- Develop directly on `main`; one commit per logical step
