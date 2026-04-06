# Docker Deployment Guide

## Prerequisites

- Docker 20.10+ (`docker --version`)
- Docker Compose v2 (`docker compose version`) — or Compose v1 (`docker-compose --version`)

---

## Build the Image

```bash
docker build -t trading-wisdom-cli:1.0.0 .
```

The build uses a **multi-stage** process:

1. **builder** stage — installs all dependencies into the system site-packages
2. **runtime** stage — copies only the installed packages and source; runs as non-root user `appuser`

The `ib_insync` optional extra is **not** installed in the Docker image. To enable IB Gateway connectivity, rebuild with:

```bash
# Edit Dockerfile line: pip install --no-cache-dir .[ib]
docker build -t trading-wisdom-cli:1.0.0-ib .
```

---

## Run Interactively (docker run)

```bash
docker run -it --rm \
  -v ~/.trading-cli:/home/appuser/.trading-cli \
  trading-wisdom-cli:1.0.0 --help
```

The volume mount maps your host config directory into the container so that:

- `~/.trading-cli/config.yaml` is read/written by the CLI (auto-created on first run)
- `~/.trading-cli/trade_log.jsonl` persists trade history across container runs

### First Run — Config Initialisation

On the first run the CLI automatically creates a default config file on the **host** via the volume mount:

```bash
docker run -it --rm \
  -v ~/.trading-cli:/home/appuser/.trading-cli \
  trading-wisdom-cli:1.0.0 config show
# Output: config written to ~/.trading-cli/config.yaml (on the host)
```

---

## Run with Docker Compose

Use `docker-compose run` for one-off commands:

```bash
# Show help
docker-compose run --rm trading-cli --help

# Paper trade — buy order
docker-compose run --rm trading-cli trade order buy 000001.SZ --qty 1000

# Backtest a strategy
docker-compose run --rm trading-cli backtest run --symbol 000001.SZ --strategy ma_cross

# Show config
docker-compose run --rm trading-cli config show
```

Start an interactive shell session (config `tty: true` is already set):

```bash
docker-compose run --rm trading-cli bash
```

---

## Live Trading (IB Gateway)

Set the IB Gateway host before running:

```bash
IB_HOST=192.168.1.100 docker-compose run --rm trading-cli trade order buy AAPL --qty 10
```

Or export variables in your shell session:

```bash
export IB_HOST=192.168.1.100
export IB_PORT=7497
export IB_CLIENT_ID=1
docker-compose run --rm trading-cli market info AAPL
```

The `docker-compose.yml` passes `IB_HOST`, `IB_PORT`, and `IB_CLIENT_ID` through to the container with safe defaults (`127.0.0.1:7497:1`).

---

## Configuration Reference

| Path (host) | Path (container) | Purpose |
|---|---|---|
| `~/.trading-cli/config.yaml` | `/home/appuser/.trading-cli/config.yaml` | CLI configuration |
| `~/.trading-cli/trade_log.jsonl` | `/home/appuser/.trading-cli/trade_log.jsonl` | Trade history log |

Both paths are provided via the volume mount `~/.trading-cli:/home/appuser/.trading-cli`.

---

## Image Details

| Property | Value |
|---|---|
| Base image | `python:3.11-slim` |
| Run user | `appuser` (non-root, UID auto-assigned) |
| Working directory | `/app` |
| Entrypoint | `trading-cli` |
| Default command | `--help` |
| Extras installed | base only (no `[ib]`) |
