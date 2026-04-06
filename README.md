# Trading Wisdom CLI

AI-powered trading framework for A-shares, Hong Kong stocks, US stocks, and options — all from your terminal.

## Features

- 12 command groups covering the full trading workflow
- Paper trading with built-in risk management
- Live trading via Interactive Brokers (IBKR) with emergency stop
- Multi-market support: A-shares (CN), Hong Kong (HK), US equities
- Options pricing with Black-Scholes, full Greeks, and strategy analysis
- Strategy backtesting with P&L, Sharpe ratio, and drawdown metrics
- Technical analysis: MA Cross, RSI, MACD, Bollinger Bands
- Strategy optimizer: grid search and genetic algorithms
- Workflow YAML pipelines for automated trading sequences
- JSON Lines audit log for all trade activity

## Quick Start

```bash
pip install trading-wisdom-cli
trading-cli --help
```

## Architecture

```
CLI Entry (trading-cli)
├── data          — Market data (Tushare/IB)
├── analyze       — Technical indicators
├── strategy      — MA/RSI/MACD/Bollinger
├── backtest      — Strategy backtesting
├── options       — Black-Scholes, Greeks
├── market        — Multi-market info (CN/HK/US)
├── trade         — Paper + live trading
├── monitor       — Price alerts
├── report        — Portfolio reporting
├── workflow      — YAML pipelines
├── config        — Configuration
└── debug         — Diagnostics
```

## Command Examples

```bash
# Fetch 60 days of data for Ping An Bank (A-share)
trading-cli data fetch 000001.SZ --days 60

# Fetch US stock data
trading-cli data fetch AAPL --market US

# Run technical analysis signals
trading-cli analyze signal 000001.SZ

# Run a backtest with MA Cross strategy
trading-cli backtest run ma_cross 000001.SZ

# Compare all strategies on a symbol, sorted by Sharpe
trading-cli backtest compare 000001.SZ --sort sharpe

# Optimize strategy parameters using genetic algorithm
trading-cli backtest optimize ma_cross 600519 --method genetic

# View options chain (9 strikes, 30 DTE)
trading-cli options chain AAPL --price 185.00

# Calculate options Greeks
trading-cli options greeks AAPL --price 185.00 --strike 190 --expiry 2026-05-16

# Paper trade: buy 1000 shares
trading-cli trade order buy 000001.SZ --qty 1000

# View account summary
trading-cli trade account

# Live trade via IBKR
trading-cli trade order buy AAPL --qty 100 --live

# Close a position at market price
trading-cli trade position close 000001.SZ

# Run portfolio risk check
trading-cli trade risk

# Emergency stop: cancel all orders and close all positions immediately
trading-cli trade emergency stop

# Show multi-market info
trading-cli market info AAPL --market US

# Show FX rate
trading-cli market fx USD CNY

# Show current configuration
trading-cli config show
```

## Live Trading (IBKR)

```bash
pip install trading-wisdom-cli[ib]
export IB_HOST=127.0.0.1
export IB_PORT=7497
trading-cli trade order buy AAPL --qty 100 --live
```

IB Gateway or Trader Workstation (TWS) must be running and accepting API connections on the configured host and port.

Emergency stop (paper mode — safe simulation):

```bash
trading-cli trade emergency stop
```

Emergency stop (live mode — acts immediately, no confirmation prompt):

```bash
trading-cli trade emergency stop --live
```

## Configuration

`~/.trading-cli/config.yaml` is auto-created on first run with sensible defaults. You can view and update it with:

```bash
trading-cli config show
trading-cli config set data.default_provider tushare
trading-cli config validate
```

## Development

```bash
git clone https://github.com/daily-engineer/trading-wisdom-cli.git
cd trading-wisdom-cli
pip install -e ".[ib]"
python -m pytest tests/ -q
python -m black trading_cli/
mypy trading_cli/ --ignore-missing-imports
```

## License

MIT
