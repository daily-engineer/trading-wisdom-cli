# Installation Guide

## Requirements

- Python 3.10 or later
- pip 22+

## Method 1: pip (recommended once published)

```bash
pip install trading-wisdom-cli
```

Note: The package is not yet published to PyPI. Use Method 2 (source install) in the meantime.

## Method 2: Source install (use this now)

```bash
git clone https://github.com/daily-engineer/trading-wisdom-cli.git
cd trading-wisdom-cli
pip install -e .
```

For live IBKR trading support:

```bash
pip install -e ".[ib]"
```

Verify the installation:

```bash
trading-cli --version
# Trading Wisdom CLI, version 1.0.0
```

## Method 3: Docker

```bash
docker build -t trading-wisdom-cli:1.0.0 .
docker run -it --rm trading-wisdom-cli:1.0.0 --help
```

To persist your config and trade logs across container runs, mount the config directory:

```bash
docker run -it --rm \
  -v "$HOME/.trading-cli:/root/.trading-cli" \
  trading-wisdom-cli:1.0.0 trade account
```

See `docker-compose.yml` in the project root for a full compose setup including IB Gateway.

## Optional dependency: live trading (IBKR)

The `[ib]` extra installs `ib_insync` which is required to connect to Interactive Brokers:

```bash
pip install trading-wisdom-cli[ib]
# or, from source:
pip install -e ".[ib]"
```

You also need IB Gateway or Trader Workstation (TWS) running with API access enabled, then export the connection details:

```bash
export IB_HOST=127.0.0.1
export IB_PORT=7497
```

## Configuration

On first run, `~/.trading-cli/config.yaml` is created automatically with sensible defaults. Inspect or edit it with:

```bash
trading-cli config show
trading-cli config set data.tushare.token YOUR_TUSHARE_TOKEN
trading-cli config validate
```

To use A-shares data (Tushare), register for a free token at https://tushare.pro and set it in the config as shown above.
