# Trading Wisdom CLI v1.0

An AI-powered, command-line driven trading framework supporting A-shares, Hong Kong stocks, US stocks, and options.

## Features

- **Multi-Market Support**: A-shares (Tushare), Hong Kong stocks, US stocks (IB API)
- **Options Analysis**: Black-Scholes pricing, full Greeks, 6 strategy templates, payoff simulation
- **Strategy Engine**: 4 built-in strategies + parameter optimizer (grid search & genetic algorithm)
- **Backtesting**: Full backtest engine with P&L, Sharpe, drawdown, win rate metrics
- **Paper Trading**: Simulated execution with risk management (position limits, stop loss, daily loss halt)
- **Real-time Monitoring**: Multi-stock dashboard, technical indicator watch, price alerts
- **Reporting**: Portfolio summary, performance reports, JSON/CSV export
- **Workflow Orchestration**: YAML pipeline definitions for automated multi-step workflows
- **Cross-Market**: Unified FX conversion, market comparison across CN/HK/US

## Quick Start

```bash
# Install
poetry install

# Configure Tushare token (for A-shares data)
trading-cli config set data.tushare.token YOUR_TOKEN

# Fetch stock data
trading-cli data fetch 000001.SZ
trading-cli data fetch 600519 --days 60

# Technical analysis
trading-cli analyze signal 000001.SZ

# Run backtest
trading-cli backtest run ma_cross 000001.SZ --days 365
trading-cli backtest compare 600519 --sort sharpe

# Optimize strategy parameters
trading-cli backtest optimize rsi 000001.SZ --method genetic

# Paper trading
trading-cli trade order buy 000001.SZ --qty 1000
trading-cli trade account
trading-cli trade risk

# Options analysis
trading-cli options chain 000001.SZ --price 11.12
trading-cli options greeks --spot 450 --strike 460 --days 30 --type call
trading-cli options strategy iron-condor --spot 450

# Multi-market
trading-cli market info US
trading-cli market compare 000001.SZ AAPL 0700.HK --base-currency CNY

# Monitoring
trading-cli monitor dashboard 000001.SZ 600519.SH
trading-cli monitor watch 000001.SZ 600519.SH 000858.SZ
```

## Command Reference

| Command | Description |
|---------|-------------|
| `data` | Fetch, validate, and manage market data |
| `config` | Manage CLI settings |
| `analyze` | Technical indicators and trading signals |
| `strategy` | Create, list, and manage trading strategies |
| `backtest` | Run backtests, compare strategies, optimize parameters |
| `trade` | Paper trading with order and risk management |
| `monitor` | Real-time dashboards, market watch, price alerts |
| `report` | Portfolio and performance reports, export |
| `options` | Options pricing, Greeks, chains, strategy analysis |
| `market` | Multi-market info, FX rates, cross-market comparison |
| `workflow` | YAML pipeline orchestration |
| `debug` | Connectivity diagnostics and system info |

## Architecture

```
┌─────────────────────────────────────┐
│     CLI Layer (Click + Rich)        │
│  12 command groups, 40+ subcommands │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│     Strategy & Analysis Layer       │
│  4 strategies + optimizer + options  │
│  Black-Scholes + Greeks + 6 spreads │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│     Execution Layer                 │
│  Backtest engine + Paper trader     │
│  Risk engine + Order management     │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│     Market Data Layer               │
│  Tushare (A-shares) + IB (HK/US)   │
│  Multi-market + FX rates            │
└─────────────────────────────────────┘
```

## Docker

```bash
docker build -t trading-cli .
docker run trading-cli data fetch 000001.SZ
docker run trading-cli options greeks --spot 11 --strike 11 --days 30
```

## Development

```bash
# Install with dev dependencies
poetry install

# Run tests
pytest tests/ -v

# Format code
black trading_cli/ tests/
```

## Project Stats

| Metric | Value |
|--------|-------|
| Python Code | 7,500+ lines |
| Test Cases | 161 |
| Command Groups | 12 |
| CLI Subcommands | 40+ |
| Built-in Strategies | 4 |
| Options Strategies | 6 |
| Markets Supported | 3 (CN/HK/US) |

## License

MIT

## Contributors

- Daily Engineer - Project lead
- Sasa - CFO / Architecture review
