"""Market sentiment commands.

Commands
--------
    trading-cli sentiment daily
    trading-cli sentiment history --days 30
    trading-cli sentiment components
    trading-cli sentiment regime
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from trading_cli.core.config import get_config
from trading_cli.core.sentiment import (
    WEIGHTS,
    classify_sentiment,
    composite_sentiment_score,
    normalize_ad_ratio,
    normalize_limit_ratio,
    normalize_northbound,
    normalize_turnover,
)

console = Console()

# ---------------------------------------------------------------------------
# Demo / fallback data
# ---------------------------------------------------------------------------

_DEMO_INDICATORS: dict = {
    "advancing": 1850,
    "declining": 1200,
    "pct_above_ma20": 62.5,
    "pct_above_ma60": 48.3,
    "turnover_current": 1.15,
    "turnover_avg": 1.0,
    "limit_up": 45,
    "limit_down": 12,
    "northbound_flow": 23.5,
    "date": "2026-04-07",
}


def _get_market_indicators(date_str: Optional[str] = None) -> dict:
    """Return a dict of raw indicator values.

    Falls back to demo values when no Tushare token is configured or when
    the real fetch is not yet implemented.
    """
    config = get_config()
    if not config.data.tushare.token:
        console.print(
            "[yellow]Notice: No Tushare token configured — showing demo data.[/yellow]"
        )
        demo = dict(_DEMO_INDICATORS)
        if date_str:
            demo["date"] = date_str
        return demo

    # Real implementation stub — falls back to demo until live fetch is built.
    demo = dict(_DEMO_INDICATORS)
    if date_str:
        demo["date"] = date_str
    return demo


# ---------------------------------------------------------------------------
# Score / component helpers
# ---------------------------------------------------------------------------


def _compute_components(ind: dict) -> dict:
    """Derive all normalised component values from a raw-indicator dict."""
    n_ad = normalize_ad_ratio(ind["advancing"], ind["declining"])
    n_ma20 = float(ind["pct_above_ma20"])
    n_ma60 = float(ind["pct_above_ma60"])
    n_turn = normalize_turnover(ind["turnover_current"], ind["turnover_avg"])
    n_limit = normalize_limit_ratio(ind["limit_up"], ind["limit_down"])
    n_north = normalize_northbound(ind["northbound_flow"])

    return {
        "advance_decline": {
            "raw": f"{ind['advancing']} / {ind['declining']}",
            "normalised": n_ad,
            "weight": WEIGHTS["advance_decline"],
            "contribution": n_ad * WEIGHTS["advance_decline"],
        },
        "pct_above_ma20": {
            "raw": f"{ind['pct_above_ma20']:.1f}%",
            "normalised": n_ma20,
            "weight": WEIGHTS["pct_above_ma20"],
            "contribution": n_ma20 * WEIGHTS["pct_above_ma20"],
        },
        "pct_above_ma60": {
            "raw": f"{ind['pct_above_ma60']:.1f}%",
            "normalised": n_ma60,
            "weight": WEIGHTS["pct_above_ma60"],
            "contribution": n_ma60 * WEIGHTS["pct_above_ma60"],
        },
        "turnover_ratio": {
            "raw": f"{ind['turnover_current']:.2f} / {ind['turnover_avg']:.2f}",
            "normalised": n_turn,
            "weight": WEIGHTS["turnover_ratio"],
            "contribution": n_turn * WEIGHTS["turnover_ratio"],
        },
        "limit_up_ratio": {
            "raw": f"{ind['limit_up']} up / {ind['limit_down']} down",
            "normalised": n_limit,
            "weight": WEIGHTS["limit_up_ratio"],
            "contribution": n_limit * WEIGHTS["limit_up_ratio"],
        },
        "northbound": {
            "raw": f"{ind['northbound_flow']:+.1f} 亿",
            "normalised": n_north,
            "weight": WEIGHTS["northbound"],
            "contribution": n_north * WEIGHTS["northbound"],
        },
    }


def _compute_score(ind: dict) -> float:
    return composite_sentiment_score(
        ad_ratio=normalize_ad_ratio(ind["advancing"], ind["declining"]),
        pct_above_ma20=ind["pct_above_ma20"],
        pct_above_ma60=ind["pct_above_ma60"],
        turnover_current=ind["turnover_current"],
        turnover_avg=ind["turnover_avg"],
        limit_up=ind["limit_up"],
        limit_down=ind["limit_down"],
        northbound_flow_val=ind["northbound_flow"],
    )


def _score_style(score: float) -> str:
    if score >= 80:
        return "bold red"
    if score >= 60:
        return "bold yellow"
    if score >= 40:
        return "white"
    if score >= 20:
        return "cyan"
    return "bold blue"


def _sparkline(values: list[float]) -> str:
    """Return an ASCII sparkline string for a list of float values."""
    blocks = " ▁▂▃▄▅▆▇█"
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo
    chars = []
    for v in values:
        if span == 0:
            idx = 4  # middle block
        else:
            idx = int((v - lo) / span * (len(blocks) - 1))
        chars.append(blocks[idx])
    return "".join(chars)


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group()
def sentiment() -> None:
    """Market breadth & sentiment indicators (composite 0-100 score)."""
    pass


# ---------------------------------------------------------------------------
# sentiment daily
# ---------------------------------------------------------------------------


@sentiment.command("daily")
@click.option(
    "--date", "date_str", default=None, help="Date (YYYY-MM-DD). Defaults to today."
)
def sentiment_daily(date_str: Optional[str]) -> None:
    """Show today's composite sentiment score and all component values.

    Example:

        trading-cli sentiment daily
    """
    ind = _get_market_indicators(date_str)
    score = _compute_score(ind)
    label, action = classify_sentiment(score)
    style = _score_style(score)
    display_date = ind.get("date", date_str or str(date.today()))

    table = Table(title=f"Market Sentiment — {display_date}", show_lines=True)
    table.add_column("Indicator", style="cyan")
    table.add_column("Raw Value", justify="right")
    table.add_column("Normalised (0-100)", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Contribution", justify="right")

    comps = _compute_components(ind)
    for name, vals in comps.items():
        table.add_row(
            name,
            str(vals["raw"]),
            f"{vals['normalised']:.1f}",
            f"{vals['weight']:.0%}",
            f"{vals['contribution']:.2f}",
        )

    console.print()
    console.print(table)
    console.print(
        Panel(
            f"[{style}]Composite Score: {score:.1f}  |  {label}[/{style}]\n"
            f"[dim]{action}[/dim]",
            title="Sentiment Summary",
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# sentiment history
# ---------------------------------------------------------------------------


@sentiment.command("history")
@click.option(
    "--days",
    "-d",
    default=30,
    type=int,
    help="Number of past days to show (default: 30).",
)
def sentiment_history(days: int) -> None:
    """Show last N days of sentiment scores as a table with a sparkline.

    Example:

        trading-cli sentiment history --days 30
    """
    import math
    import random

    random.seed(42)

    # Generate simulated history around the demo score (no real historical API)
    base_ind = _get_market_indicators()
    base_score = _compute_score(base_ind)

    records = []
    today = date.today()
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        # Simulate slight daily variation for history
        noise = random.uniform(-8.0, 8.0)
        score = max(0.0, min(100.0, base_score + noise))
        label, _ = classify_sentiment(score)
        records.append((str(d), score, label))

    scores = [r[1] for r in records]
    spark = _sparkline(scores)

    table = Table(title=f"Sentiment History — last {days} days", show_lines=False)
    table.add_column("Date", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Classification", justify="left")

    for d_str, score, label in records:
        style = _score_style(score)
        table.add_row(
            d_str, f"[{style}]{score:.1f}[/{style}]", f"[{style}]{label}[/{style}]"
        )

    console.print()
    console.print(table)
    console.print(f"\nSparkline: {spark}")
    console.print(
        f"  Range: {min(scores):.1f} – {max(scores):.1f}  |  Avg: {sum(scores)/len(scores):.1f}\n"
    )


# ---------------------------------------------------------------------------
# sentiment components
# ---------------------------------------------------------------------------


@sentiment.command("components")
def sentiment_components() -> None:
    """Detailed breakdown: raw value, normalised, weight, and contribution.

    Example:

        trading-cli sentiment components
    """
    ind = _get_market_indicators()
    score = _compute_score(ind)
    label, _ = classify_sentiment(score)

    table = Table(title="Sentiment Component Breakdown", show_lines=True)
    table.add_column("Component", style="cyan", min_width=20)
    table.add_column("Raw Value", justify="right")
    table.add_column("Normalised", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Contribution", justify="right")
    table.add_column("Bar", no_wrap=True)

    comps = _compute_components(ind)
    for name, vals in comps.items():
        n = vals["normalised"]
        bar_len = int(n / 5)
        bar = "█" * bar_len
        table.add_row(
            name,
            str(vals["raw"]),
            f"{n:.1f}",
            f"{vals['weight']:.0%}",
            f"{vals['contribution']:.2f}",
            bar,
        )

    console.print()
    console.print(table)
    console.print(f"\n[bold]Total composite score:[/bold] {score:.1f}  ({label})\n")


# ---------------------------------------------------------------------------
# sentiment regime
# ---------------------------------------------------------------------------


@sentiment.command("regime")
def sentiment_regime() -> None:
    """Show current market regime and recommended action.

    Example:

        trading-cli sentiment regime
    """
    ind = _get_market_indicators()
    score = _compute_score(ind)
    label, action = classify_sentiment(score)
    style = _score_style(score)

    console.print()
    console.print(
        Panel(
            f"[{style}]Regime:  {label}[/{style}]\n"
            f"Score:   {score:.1f} / 100\n\n"
            f"[bold]Recommended Action:[/bold]\n{action}",
            title="Market Regime",
            border_style=style,
        )
    )
    console.print()
