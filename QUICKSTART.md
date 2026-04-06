# Quick Start — 5 Minutes to Your First Trade

## Step 1: Install from source

```bash
git clone https://github.com/daily-engineer/trading-wisdom-cli.git
cd trading-wisdom-cli
pip install -e .
```

## Step 2: Verify the installation

```bash
trading-cli --version
```

Expected output:

```
Trading Wisdom CLI, version 1.0.0
```

## Step 3: Fetch market data

```bash
trading-cli data fetch 000001.SZ
```

This fetches the last 30 days of daily OHLCV data for Ping An Bank (A-share). For a longer window:

```bash
trading-cli data fetch 000001.SZ --days 90
```

## Step 4: Analyze technical signals

```bash
trading-cli analyze signal 000001.SZ
```

This computes RSI, MACD, and Bollinger Band signals and prints a buy/sell/neutral summary.

## Step 5: Run a backtest

```bash
trading-cli backtest run ma_cross 000001.SZ
```

The engine runs a Moving Average Crossover strategy on the last 365 days and reports total return, Sharpe ratio, maximum drawdown, and win rate.

## Step 6: Place a paper trade

```bash
trading-cli trade order buy 000001.SZ --qty 1000
```

Paper mode is the default — no real money is involved. The order fills immediately at the last known price.

## Step 7: Check your account

```bash
trading-cli trade account
```

Shows cash balance, open positions, market value, and total P&L for the paper trading account.

## Step 8: View an options chain

```bash
trading-cli options chain AAPL --price 185.00
```

Displays calls and puts across 9 strikes centered on the spot price, with Black-Scholes prices and full Greeks (delta, gamma, theta, vega, rho).

## Step 9: Trigger an emergency stop

```bash
trading-cli trade emergency stop
```

Immediately cancels all open orders and closes all positions at current prices (paper mode). Use `--live` to execute against a real IBKR account.

---

## Next Steps

- Set a Tushare token for live A-shares data: `trading-cli config set data.tushare.token YOUR_TOKEN`
- Optimize strategy parameters: `trading-cli backtest optimize ma_cross 000001.SZ`
- Enable live IBKR trading: `pip install -e ".[ib]"` then `trading-cli trade order buy AAPL --qty 10 --live`
- Automate multi-step workflows: `trading-cli workflow run my_workflow.yaml`
- Monitor prices in real time: `trading-cli monitor watch 000001.SZ 600519`
- Full command reference: `trading-cli --help` or `trading-cli COMMAND --help`
