"""Capital flow monitoring commands — 主力资金流向."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import click
import pandas as pd
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading_cli.core.config import get_config
from trading_cli.core.capital_flow import (
    calculate_net_inflow,
    calculate_flow_intensity,
    detect_signal,
    calculate_streak,
)

console = Console()

# Sector ETF proxies — used instead of aggregating individual stocks
SECTOR_ETFS = {
    "医疗": "512010.SH",
    "科技": "159941.SZ",
    "金融": "512880.SH",
    "消费": "512690.SH",
    "新能源": "516160.SH",
    "地产": "515000.SH",
    "宽基": "510300.SH",
}


def _fetch_capital_flow(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """Fetch capital flow data from Tushare moneyflow endpoint.

    Returns a DataFrame with columns:
        trade_date, close, buy_sm_vol, sell_sm_vol,
        buy_md_vol, sell_md_vol, buy_lg_vol, sell_lg_vol,
        buy_elg_vol, sell_elg_vol, net_mf_vol
    Returns None if token is missing or fetch fails.
    """
    config = get_config()
    token = config.data.tushare.token
    if not token:
        console.print(
            "[red]Tushare Token 未配置。"
            "请运行: trading-cli config set data.tushare.token <YOUR_TOKEN>[/red]"
        )
        return None

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    params = {
        "api_name": "moneyflow",
        "token": token,
        "params": {
            "ts_code": symbol,
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
        },
        "fields": (
            "ts_code,trade_date,close,"
            "buy_sm_vol,sell_sm_vol,"
            "buy_md_vol,sell_md_vol,"
            "buy_lg_vol,sell_lg_vol,"
            "buy_elg_vol,sell_elg_vol,net_mf_vol"
        ),
    }

    try:
        resp = requests.post(
            config.data.tushare.api_url,
            json=params,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
    except (requests.RequestException, ValueError) as exc:
        console.print(f"[red]请求失败: {exc}[/red]")
        return None

    if result.get("code") != 0:
        msg = result.get("msg", "unknown error")
        console.print(f"[red]Tushare API 错误: {msg}[/red]")
        return None

    fields = result["data"]["fields"]
    items = result["data"]["items"] or []
    if not items:
        return pd.DataFrame()

    df = pd.DataFrame(items, columns=fields)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").reset_index(drop=True)

    # Ensure numeric columns
    numeric_cols = [
        "close",
        "buy_sm_vol",
        "sell_sm_vol",
        "buy_md_vol",
        "sell_md_vol",
        "buy_lg_vol",
        "sell_lg_vol",
        "buy_elg_vol",
        "sell_elg_vol",
        "net_mf_vol",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns (net_inflow, flow_intensity, signal, price_change)."""
    df = df.copy()
    df["price_change"] = df["close"].pct_change().fillna(0.0)
    df["net_inflow"] = calculate_net_inflow(df)

    # Use net_mf_vol as total_vol proxy if available, else sum all buy/sell vols
    total_vol = (
        df["net_mf_vol"].abs()
        if "net_mf_vol" in df.columns
        else (
            df["buy_lg_vol"]
            + df["sell_lg_vol"]
            + df["buy_elg_vol"]
            + df["sell_elg_vol"]
        ).abs()
    )
    df["flow_intensity"] = calculate_flow_intensity(df["net_inflow"], total_vol)
    df["signal"] = detect_signal(df["price_change"], df["net_inflow"])
    return df


@click.group("capital-flow")
def capital_flow() -> None:
    """💰 Capital Flow — 主力资金流向监控."""
    pass


@capital_flow.command("stock")
@click.argument("code")
@click.option("--days", "-d", default=30, show_default=True, help="Lookback days.")
def stock_flow(code: str, days: int) -> None:
    """Show capital flow for a single stock.

    Examples:

        trading-cli capital-flow stock 000001.SZ --days 30

        trading-cli capital-flow stock 600519.SH
    """
    # Normalise symbol
    symbol = code.upper()
    if "." not in symbol:
        symbol = f"{symbol}.SH" if symbol.startswith("6") else f"{symbol}.SZ"

    df = _fetch_capital_flow(symbol, days)
    if df is None:
        raise SystemExit(1)
    if df.empty:
        console.print(f"[yellow]未找到 {symbol} 的资金流向数据[/yellow]")
        return

    df = _enrich(df)
    streak = calculate_streak(df["net_inflow"])

    table = Table(title=f"资金流向 — {symbol} (近 {days} 天)", show_lines=True)
    table.add_column("日期", style="dim")
    table.add_column("收盘价", justify="right")
    table.add_column("主力净流入 (万)", justify="right")
    table.add_column("流入强度", justify="right")
    table.add_column("信号", justify="center")

    for _, row in df.tail(20).iterrows():
        inflow_wan = row["net_inflow"] / 10000
        inflow_str = (
            f"[green]+{inflow_wan:,.1f}[/green]"
            if inflow_wan >= 0
            else f"[red]{inflow_wan:,.1f}[/red]"
        )
        sig_color = {"吸筹": "green", "派发": "red", "中性": "dim"}.get(
            row["signal"], "dim"
        )
        table.add_row(
            str(row["trade_date"])[:10],
            f"{row['close']:.2f}",
            inflow_str,
            f"{row['flow_intensity']:.1f}%",
            f"[{sig_color}]{row['signal']}[/{sig_color}]",
        )

    console.print()
    console.print(table)

    streak_desc = (
        f"[green]连续 {streak} 天净流入[/green]"
        if streak > 0
        else (
            f"[red]连续 {abs(streak)} 天净流出[/red]"
            if streak < 0
            else "[dim]当日持平[/dim]"
        )
    )
    console.print(f"\n  当前趋势: {streak_desc}\n")


@capital_flow.command("sector")
@click.option("--top", "-n", default=10, show_default=True, help="Show top N sectors.")
def sector_flow(top: int) -> None:
    """Show capital flow by sector (via ETF proxies).

    Examples:

        trading-cli capital-flow sector --top 5
    """
    rows = []
    for sector_name, etf_code in list(SECTOR_ETFS.items())[:top]:
        df = _fetch_capital_flow(etf_code, 5)
        if df is None:
            return  # token error already printed
        if df.empty:
            rows.append((sector_name, etf_code, float("nan"), float("nan"), "N/A"))
            continue
        df = _enrich(df)
        latest = df.iloc[-1]
        inflow_wan = latest["net_inflow"] / 10000
        rows.append(
            (
                sector_name,
                etf_code,
                inflow_wan,
                latest["flow_intensity"],
                latest["signal"],
            )
        )

    # Sort by net inflow descending
    rows_sorted = sorted(
        rows, key=lambda r: (r[2] if not pd.isna(r[2]) else float("-inf")), reverse=True
    )

    table = Table(title="板块资金流向 (ETF 代理)", show_lines=True)
    table.add_column("板块", style="bold cyan")
    table.add_column("ETF", style="dim")
    table.add_column("主力净流入 (万)", justify="right")
    table.add_column("流入强度", justify="right")
    table.add_column("信号", justify="center")

    for sector_name, etf_code, inflow_wan, intensity, signal in rows_sorted:
        if pd.isna(inflow_wan):
            table.add_row(sector_name, etf_code, "[yellow]N/A[/yellow]", "-", "-")
            continue
        inflow_str = (
            f"[green]+{inflow_wan:,.1f}[/green]"
            if inflow_wan >= 0
            else f"[red]{inflow_wan:,.1f}[/red]"
        )
        sig_color = {"吸筹": "green", "派发": "red", "中性": "dim"}.get(signal, "dim")
        table.add_row(
            sector_name,
            etf_code,
            inflow_str,
            f"{intensity:.1f}%",
            f"[{sig_color}]{signal}[/{sig_color}]",
        )

    console.print()
    console.print(table)
    console.print()


@capital_flow.command("alerts")
@click.option(
    "--divergence",
    "mode",
    flag_value="divergence",
    default=True,
    help="Show 吸筹/派发 divergence alerts.",
)
@click.option("--days", "-d", default=30, show_default=True, help="Lookback days.")
def alerts(mode: str, days: int) -> None:
    """Show capital flow divergence alerts across sector ETFs.

    Detects:
      吸筹 — 3+ consecutive inflow days with price decline (smart accumulation)
      派发 — 3+ consecutive outflow days with price rise (distribution)

    Examples:

        trading-cli capital-flow alerts --divergence
    """
    console.print()
    console.print(Panel("[bold]资金流向背离预警[/bold]", border_style="yellow"))

    found_any = False
    for sector_name, etf_code in SECTOR_ETFS.items():
        df = _fetch_capital_flow(etf_code, days)
        if df is None:
            return
        if df.empty:
            continue
        df = _enrich(df)

        # Check last 3+ rows for divergence
        if len(df) < 3:
            continue

        last3 = df.tail(3)
        inflows = last3["net_inflow"].tolist()
        price_chgs = last3["price_change"].tolist()

        all_inflow = all(v > 0 for v in inflows)
        all_outflow = all(v < 0 for v in inflows)
        price_down = price_chgs[-1] < 0
        price_up = price_chgs[-1] > 0

        if all_inflow and price_down:
            console.print(
                f"  [green][吸筹][/green] {sector_name} ({etf_code}) — "
                f"连续3天净流入，但价格下跌 {price_chgs[-1]*100:.2f}%"
            )
            found_any = True
        elif all_outflow and price_up:
            console.print(
                f"  [red][派发][/red] {sector_name} ({etf_code}) — "
                f"连续3天净流出，但价格上涨 {price_chgs[-1]*100:.2f}%"
            )
            found_any = True

    if not found_any:
        console.print("  [dim]当前无背离信号[/dim]")
    console.print()


@capital_flow.command("streak")
@click.option(
    "--threshold",
    "-t",
    default=5,
    show_default=True,
    help="Minimum streak length to report.",
)
def streak_cmd(threshold: int) -> None:
    """Show stocks/ETFs with consecutive capital flow streaks ≥ threshold.

    Examples:

        trading-cli capital-flow streak --threshold 5
    """
    rows = []
    for sector_name, etf_code in SECTOR_ETFS.items():
        df = _fetch_capital_flow(etf_code, threshold * 2 + 10)
        if df is None:
            return
        if df.empty:
            continue
        df = _enrich(df)
        streak = calculate_streak(df["net_inflow"])
        if abs(streak) >= threshold:
            rows.append((sector_name, etf_code, streak))

    if not rows:
        console.print(f"\n  [dim]无连续 {threshold} 天以上的资金流向记录[/dim]\n")
        return

    rows_sorted = sorted(rows, key=lambda r: abs(r[2]), reverse=True)

    table = Table(title=f"连续资金流向 (阈值 ≥ {threshold} 天)", show_lines=True)
    table.add_column("板块", style="bold cyan")
    table.add_column("ETF", style="dim")
    table.add_column("连续天数", justify="right")
    table.add_column("方向", justify="center")

    for sector_name, etf_code, streak in rows_sorted:
        direction = "[green]净流入[/green]" if streak > 0 else "[red]净流出[/red]"
        streak_str = (
            f"[green]{streak}[/green]" if streak > 0 else f"[red]{streak}[/red]"
        )
        table.add_row(sector_name, etf_code, streak_str, direction)

    console.print()
    console.print(table)
    console.print()
