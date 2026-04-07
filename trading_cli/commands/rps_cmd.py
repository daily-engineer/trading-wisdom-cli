"""ETF RPS (Relative Price Strength) commands.

Commands
--------
    trading-cli rps list [--window 60] [--top 20]
    trading-cli rps sector
    trading-cli rps trend <etf_code> [--days 120]
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import click
import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, Market, registry
from trading_cli.core.rps import (
    DEFAULT_ETF_UNIVERSE,
    SECTOR_MAP,
    calculate_rps,
    classify_grade,
    composite_rps,
)
from trading_cli.core.tushare_provider import TushareProvider

console = Console()

# ---------------------------------------------------------------------------
# Grade colour mapping for Rich
# ---------------------------------------------------------------------------

_GRADE_STYLE: dict[str, str] = {
    "A": "bold green",
    "B": "yellow",
    "C": "white",
    "D": "red",
    "N/A": "dim",
}


def _grade_style(grade: str) -> str:
    return _GRADE_STYLE.get(grade, "white")


# ---------------------------------------------------------------------------
# Provider helpers
# ---------------------------------------------------------------------------


def _ensure_providers() -> None:
    """Register Tushare provider if not already registered."""
    if "tushare" not in registry.list_providers():
        cfg = get_config()
        registry.register(TushareProvider(cfg.data.tushare))


def _fetch_prices(
    codes: list[str],
    days: int,
) -> pd.DataFrame:
    """Fetch close prices for a list of ETF codes.

    Returns a DataFrame with dates as index and ETF codes as columns.
    Missing or erroring ETFs are silently omitted.
    """
    _ensure_providers()
    end = date.today()
    start = end - timedelta(days=days + 50)  # buffer for non-trading days

    close_series: dict[str, pd.Series] = {}

    try:
        provider = registry.get("tushare")
    except (ValueError, KeyError):
        return pd.DataFrame()

    for code in codes:
        request = DataFetchRequest(
            symbol=code,
            start_date=start,
            end_date=end,
            market=Market.CN,
        )
        try:
            result = provider.fetch_stock_daily(request)
            if result.is_empty:
                continue
            df = result.data
            # Normalise date column — could be 'trade_date' or the index
            if "trade_date" in df.columns:
                df = df.set_index("trade_date")
            close_series[code] = df["close"].astype(float)
        except Exception:
            # Skip ETFs that fail (network, missing data, etc.)
            continue

    if not close_series:
        return pd.DataFrame()

    prices = pd.DataFrame(close_series)
    prices.index = pd.to_datetime(prices.index)
    prices.sort_index(inplace=True)
    return prices


def _fmt_score(val: float) -> str:
    """Format an RPS score, showing N/A for NaN."""
    if np.isnan(val):
        return "[dim]N/A[/dim]"
    return f"{val:.1f}"


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group()
def rps():
    """ETF RPS — Relative Price Strength scoring for A-share ETFs."""
    pass


# ---------------------------------------------------------------------------
# rps list
# ---------------------------------------------------------------------------


@rps.command("list")
@click.option(
    "--window",
    "-w",
    type=click.Choice(["20", "60", "120", "250"]),
    default="60",
    help="Primary RPS time window (default: 60d).",
)
@click.option(
    "--top",
    "-t",
    type=int,
    default=20,
    help="Show top N ETFs (default: 20).",
)
def rps_list(window: str, top: int) -> None:
    """List ETFs ranked by RPS score.

    Example:

        trading-cli rps list --window 60 --top 20
    """
    w = int(window)
    lookback = max(w + 50, 300)  # fetch enough history

    console.print(
        f"\n[bold cyan]Fetching RPS data (window={w}d, top={top})…[/bold cyan]"
    )

    prices = _fetch_prices(DEFAULT_ETF_UNIVERSE, days=lookback)

    if prices.empty:
        console.print(
            "[yellow]No data available. Check your data provider configuration.[/yellow]"
        )
        return

    df = composite_rps(prices)
    df = df.head(top)

    window_col = f"rps_{w}"

    table = Table(
        title=f"ETF RPS Ranking — {w}d window (top {top})",
        show_lines=False,
    )
    table.add_column("Rank", justify="right", style="dim", width=5)
    table.add_column("Code", style="cyan")
    table.add_column("Sector")
    table.add_column(f"RPS-{w}", justify="right")
    table.add_column("RPS-Composite", justify="right")
    table.add_column("Grade", justify="center")

    for i, row in enumerate(df.itertuples(), start=1):
        grade = str(row.grade)
        style = _grade_style(grade)
        sector = SECTOR_MAP.get(row.code, "其他")
        w_val = getattr(row, window_col, np.nan)
        table.add_row(
            str(i),
            row.code,
            sector,
            _fmt_score(float(w_val)),
            _fmt_score(float(row.rps_composite)),
            f"[{style}]{grade}[/{style}]",
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# rps sector
# ---------------------------------------------------------------------------


@rps.command("sector")
def rps_sector() -> None:
    """Show average RPS scores grouped by sector.

    Example:

        trading-cli rps sector
    """
    console.print("\n[bold cyan]Fetching sector RPS data…[/bold cyan]")

    prices = _fetch_prices(DEFAULT_ETF_UNIVERSE, days=300)

    if prices.empty:
        console.print(
            "[yellow]No data available. Check your data provider configuration.[/yellow]"
        )
        return

    df = composite_rps(prices)

    # Add sector column
    df["sector"] = df["code"].map(lambda c: SECTOR_MAP.get(c, "其他"))

    sector_summary = (
        df.groupby("sector")["rps_composite"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "avg_rps", "count": "n"})
        .reset_index()
        .sort_values("avg_rps", ascending=False)
    )

    table = Table(title="ETF Sector RPS Summary", show_lines=False)
    table.add_column("Sector", style="cyan")
    table.add_column("ETF Count", justify="right")
    table.add_column("Avg RPS", justify="right")
    table.add_column("Grade", justify="center")

    for _, row in sector_summary.iterrows():
        avg = float(row["avg_rps"])
        grade = classify_grade(avg) if not np.isnan(avg) else "N/A"
        style = _grade_style(grade)
        table.add_row(
            str(row["sector"]),
            str(int(row["n"])),
            _fmt_score(avg),
            f"[{style}]{grade}[/{style}]",
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# rps trend
# ---------------------------------------------------------------------------


@rps.command("trend")
@click.argument("etf_code")
@click.option(
    "--days",
    "-d",
    type=int,
    default=120,
    help="Number of calendar days to look back (default: 120).",
)
def rps_trend(etf_code: str, days: int) -> None:
    """Show RPS trend for a single ETF over time.

    Example:

        trading-cli rps trend 510300.SH --days 120
    """
    console.print(f"\n[bold cyan]Fetching trend for {etf_code} ({days}d)…[/bold cyan]")

    # Fetch the target ETF plus the universe for cross-sectional ranking
    all_codes = list({etf_code} | set(DEFAULT_ETF_UNIVERSE))
    prices = _fetch_prices(all_codes, days=days + 100)

    if prices.empty or etf_code not in prices.columns:
        console.print(f"[yellow]No data for {etf_code}.[/yellow]")
        return

    # Compute rolling RPS (20d window) over last `days` trading days
    trading_days = min(days, len(prices) - 21)
    if trading_days < 5:
        console.print(f"[yellow]Insufficient data for trend (need > 20 days).[/yellow]")
        return

    trend_records = []
    step = max(1, trading_days // 20)  # sample ~20 data points
    for i in range(0, trading_days, step):
        slice_end = len(prices) - i
        if slice_end < 21:
            break
        sub = prices.iloc[:slice_end]
        rps = calculate_rps(sub, window=20, smooth=1)
        score = rps.get(etf_code, np.nan)
        trend_date = prices.index[slice_end - 1]
        trend_records.append((trend_date, score))

    trend_records.reverse()

    table = Table(
        title=f"RPS-20 Trend: {etf_code}",
        show_lines=False,
    )
    table.add_column("Date", style="dim")
    table.add_column("RPS-20", justify="right")
    table.add_column("Grade", justify="center")
    table.add_column("Bar", no_wrap=True)

    for dt, score in trend_records:
        if np.isnan(score):
            grade = "N/A"
            bar = ""
        else:
            grade = classify_grade(score)
            bar_len = int(score / 5)
            bar = "█" * bar_len

        style = _grade_style(grade)
        date_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)
        table.add_row(
            date_str,
            _fmt_score(score) if not np.isnan(score) else "[dim]N/A[/dim]",
            f"[{style}]{grade}[/{style}]",
            f"[{style}]{bar}[/{style}]",
        )

    console.print(table)
    console.print()
