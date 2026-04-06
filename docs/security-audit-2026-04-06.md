# Security Audit Report

**Date:** 2026-04-06
**Auditor:** Automated (Claude Code)
**Scope:** Full codebase — trading-wisdom-cli v1.0.0

---

## Executive Summary

The codebase passes all security checks. No hardcoded credentials, unsafe code injection vectors, or unsafe defaults were found. One low-severity informational note is documented in Check 2 regarding the debug command exposing the first 8 characters of the Tushare token — acceptable for a diagnostic tool but noted for awareness.

---

## Check 1: Credential Management

### IB Credentials (`core/live_trader.py`)

| Item | Finding | Status |
|------|---------|--------|
| `IB_HOST` | Read from `os.environ.get("IB_HOST", "127.0.0.1")` — no hardcoded value | PASS |
| `IB_PORT` | Read from `os.environ.get("IB_PORT", "7497")` — default is a local port, not a secret | PASS |
| `IB_CLIENT_ID` | Read from `os.environ.get("IB_CLIENT_ID", "1")` — not a secret credential | PASS |
| Hardcoded token/password | None found | PASS |

### Tushare Token (`core/tushare_provider.py`, `core/config.py`)

| Item | Finding | Status |
|------|---------|--------|
| Token storage | `TushareConfig.token` defaults to `""` and is populated from `~/.trading-cli/config.yaml` via `yaml.safe_load` | PASS |
| Token in source | No token value assigned in source code — field is always empty string at definition | PASS |
| Token in API call | Passed as a JSON body field to `api.tushare.pro` over HTTPS — not in URL or log | PASS |

### LLM API Key (`core/config.py`)

| Item | Finding | Status |
|------|---------|--------|
| `llm_api_key` | Defined as `llm_api_key: str = ""` — populated only from user config file | PASS |
| Hardcoded value | None | PASS |

**Overall Check 1: PASS** — All credentials are loaded exclusively from environment variables or user-managed config files. No secrets are embedded in source code.

---

## Check 2: Sensitive Data in Logs

### `core/trade_logger.py`

| Item | Finding | Status |
|------|---------|--------|
| `account_id` storage | Stored as `account_id[-4:]` (last 4 chars only) under key `account_id_suffix` | PASS |
| Full account ID in log | Never written to log file | PASS |
| Token/password in log | Not applicable — logger only handles `Order` objects | PASS |

### `core/live_trader.py`

| Item | Finding | Status |
|------|---------|--------|
| `logging.warning` (line 168) | Logs `order_id` and exception message only — no credentials or account data | PASS |
| `logging.error` (line 211) | Logs `symbol` and exception message during emergency stop — no sensitive data | PASS |
| Full account ID exposed | `self._account_id` passed to `logger.log()` which truncates it — never printed | PASS |

### `commands/trade_cmd.py`

| Item | Finding | Status |
|------|---------|--------|
| `console.print` calls | Print filled prices, symbols, quantities, and order IDs — no tokens or account IDs | PASS |
| Account display (`trade account`) | Displays paper account ID from `PaperTrader` — a locally generated ID, not an IBKR account number | PASS |

### `commands/debug_cmd.py` — Informational Note

| Item | Finding | Status |
|------|---------|--------|
| Token display (line 59) | Prints `config.data.tushare.token[:8] + "..."` to console during `debug connectivity` | INFO |

> **Note:** The `debug connectivity` command intentionally exposes the first 8 characters of the Tushare token to help users verify the correct token is configured. This is a diagnostic command and is consistent with standard CLI patterns (similar to `aws configure list`). It does not appear in logs or audit files. Acceptable as-is.

**Overall Check 2: PASS** — No console or logging calls expose full account IDs, tokens, or connection strings. The trade audit log stores only the last 4 characters of the account ID.

---

## Check 3: Safe Defaults

### Commands with `--live` Flag

| Command | `--live` Default | Confirmation Required | Notes |
|---------|-----------------|----------------------|-------|
| `trade order buy` | `False` | Yes — prompts with bold red warning, `default=False` | Can skip with `--yes` |
| `trade order sell` | `False` | Yes — prompts with bold red warning, `default=False` | Can skip with `--yes` |
| `position close` | `False` | Yes — prompts with bold red warning, `default=False` | Can skip with `--yes` |
| `emergency stop` | `False` | No confirmation — intentionally immediate by design | See note |

> **Note on `emergency stop`:** The emergency stop command deliberately skips the confirmation prompt and acts immediately. This is correct by design — a stop that requires confirmation under panic conditions is dangerous. The `--live` flag must still be explicitly passed to trigger live-mode execution, so the default remains safe (paper mode).

### `workflow run --dry-run`

| Item | Finding | Status |
|------|---------|--------|
| Default behavior | Executes pipeline steps (execution is the default mode) | CORRECT |
| `--dry-run` flag | Opt-in flag that shows steps without executing | CORRECT |
| Assessment | Paper trading is the safe default for all trade commands; `--dry-run` in workflows is orthogonal to this and correctly implemented as an explicit opt-in | PASS |

**Overall Check 3: PASS** — All live-money commands require `--live` to be explicitly set. Buy, sell, and close operations require additional interactive confirmation by default.

---

## Check 4: Dependency Licenses

| Dependency | License | OSI Approved | Notes |
|-----------|---------|-------------|-------|
| click | BSD-3-Clause | Yes | |
| rich | MIT | Yes | |
| pydantic | MIT | Yes | |
| pyyaml | MIT | Yes | |
| pandas | BSD-3-Clause | Yes | |
| numpy | BSD-3-Clause | Yes | |
| requests | Apache-2.0 | Yes | |
| ib_insync | BSD-2-Clause | Yes | Optional extra; no Commons Clause |
| pytest | MIT | Yes | Dev dependency |
| black | MIT | Yes | Dev dependency |
| mypy | MIT | Yes | Dev dependency |
| pylint | GPL-2.0 | Yes | Dev-only; does not affect distribution |
| pytest-cov | MIT | Yes | Dev dependency |

> **Commons Clause / SSPL check:** None of the listed dependencies use Commons Clause, SSPL, or any other non-OSI-approved restriction. `pylint` is GPL-2.0 but is a dev-only tool and is not bundled with the distributed package.

**Overall Check 4: PASS** — All runtime and optional dependencies use permissive OSI-approved licenses. No license compatibility concerns.

---

## Check 5: Code Injection and Path Traversal

### `subprocess` Calls

Searched all Python source files under `trading_cli/` for `subprocess`:

| Finding | Status |
|---------|--------|
| No `subprocess` calls found anywhere in the codebase | PASS |

### `eval()` / `exec()` Calls

Searched all Python source files for `eval(` and `exec(`:

| Finding | Status |
|---------|--------|
| No `eval()` or `exec()` calls found anywhere in the codebase | PASS |

### SQL Injection

Searched all Python source files for SQL keywords (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) and `sqlite`:

| Finding | Status |
|---------|--------|
| No SQL queries or database connections found — the project uses flat files (YAML, JSONL) and in-memory structures only | PASS |

### Path Traversal (`workflow_cmd.py`)

| Item | Finding | Status |
|------|---------|--------|
| `workflow run` pipeline file | Uses `click.Path(exists=True)` which validates the path exists; file is opened with `open(pipeline_file, "r")` — no path manipulation | PASS |
| `workflow list` | Scans `~/.trading-wisdom/workflows/*.yaml` using `Path.glob()` — bounded to a fixed directory | PASS |
| YAML loading | Uses `yaml.safe_load()` throughout — not `yaml.load()` with a full Loader, which prevents arbitrary Python object deserialization | PASS |
| Variable substitution in pipeline | Uses `str.format(**variables)` with user-supplied key=value pairs — variables are substituted into CLI command strings, not shell commands; execution goes through `cli.main()` (Click), not `subprocess` or `os.system()` | PASS |

> **Note on workflow variable substitution:** While `str.format(**variables)` with user-controlled input could theoretically be used for format-string abuse, the result is passed to `cli.main(cmd.split(), standalone_mode=False)` — Click's own argument parser — not to a shell. This eliminates shell injection risk. The only risk would be passing unexpected CLI flags, which Click validates against its own option definitions.

**Overall Check 5: PASS** — No shell injection, eval/exec, SQL injection, or path traversal vulnerabilities found.

---

## Verdict

**Overall: PASS**

All five security checks pass. The codebase demonstrates sound credential hygiene, appropriate log masking, safe defaults for all live-trading operations, clean dependency licenses, and no code injection vectors. The single informational note (partial token display in `debug connectivity`) is a deliberate UX feature and does not constitute a vulnerability.

**Action items:** None required.
