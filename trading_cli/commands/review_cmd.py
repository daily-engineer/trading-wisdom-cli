"""Market review command.

Commands
--------
    trading-cli review daily                     # auto mode
    trading-cli review daily --mode intraday     # force intraday
    trading-cli review daily --mode close        # force close
    trading-cli review daily --json              # JSON output
"""

from __future__ import annotations

from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from trading_cli.core.market_review import (
    fetch_indices,
    fetch_market_breadth,
    fetch_sector_board,
    format_change,
    render_json,
    render_markdown,
)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_mode(mode: str) -> str:
    """Resolve 'auto' to 'intraday' or 'close' based on current time."""
    if mode != "auto":
        return mode
    now = datetime.now()
    if now.hour < 15 or (now.hour == 15 and now.minute < 30):
        return "intraday"
    return "close"


def _print_rich_review(
    indices: list,
    sectors_industry: list,
    sectors_concept: list,
    breadth: dict,
    mode: str,
) -> None:
    """Print a rich-formatted market review to the terminal."""
    mode_label = "盘中行情" if mode == "intraday" else "收盘复盘"
    console.print(f"\n[bold cyan]📊 A 股日报 — {mode_label}[/bold cyan]\n")

    # --- Indices table ---
    idx_table = Table(title="主要指数", show_header=True, header_style="bold magenta")
    idx_table.add_column("指数", style="cyan", no_wrap=True)
    idx_table.add_column("最新", justify="right")
    idx_table.add_column("涨跌幅", justify="right")
    idx_table.add_column("成交额(亿)", justify="right")

    for idx in indices:
        if idx.get("error"):
            idx_table.add_row(idx.get("code", "?"), "-", "-", "-")
        else:
            pct = idx.get("change_pct", 0.0)
            if pct > 0:
                pct_str = f"[green]+{pct:.2f}%[/green]"
            elif pct < 0:
                pct_str = f"[red]{pct:.2f}%[/red]"
            else:
                pct_str = f"{pct:.2f}%"
            idx_table.add_row(
                idx.get("name", idx.get("code", "?")),
                f"{idx.get('current', 0.0):.2f}",
                pct_str,
                f"{idx.get('amount_yi', 0.0):.1f}",
            )

    console.print(idx_table)

    # --- Industry sectors ---
    if sectors_industry:
        sec_table = Table(
            title="行业板块 TOP5", show_header=True, header_style="bold yellow"
        )
        sec_table.add_column("板块", style="cyan")
        sec_table.add_column("涨跌幅", justify="right")
        for s in sectors_industry[:5]:
            pct = s.get("change_pct", 0.0)
            if pct > 0:
                pct_str = f"[green]+{pct:.2f}%[/green]"
            elif pct < 0:
                pct_str = f"[red]{pct:.2f}%[/red]"
            else:
                pct_str = f"{pct:.2f}%"
            sec_table.add_row(s.get("name", "?"), pct_str)
        console.print(sec_table)
    else:
        console.print("[yellow]行业板块：数据暂不可用（东财接口超时）[/yellow]")

    # --- Concept sectors ---
    if sectors_concept:
        con_table = Table(
            title="概念板块 TOP5", show_header=True, header_style="bold blue"
        )
        con_table.add_column("板块", style="cyan")
        con_table.add_column("涨跌幅", justify="right")
        for s in sectors_concept[:5]:
            pct = s.get("change_pct", 0.0)
            if pct > 0:
                pct_str = f"[green]+{pct:.2f}%[/green]"
            elif pct < 0:
                pct_str = f"[red]{pct:.2f}%[/red]"
            else:
                pct_str = f"{pct:.2f}%"
            con_table.add_row(s.get("name", "?"), pct_str)
        console.print(con_table)

    # --- Breadth ---
    console.print("\n[bold]市场宽度[/bold]")
    if breadth.get("advancing", 0) or breadth.get("declining", 0):
        console.print(
            f"  上涨: {breadth['advancing']}  下跌: {breadth['declining']}  "
            f"平: {breadth['flat']}"
        )
        console.print(f"  涨停: {breadth['limit_up']}  跌停: {breadth['limit_down']}")
        console.print(f"  北向资金: {breadth['northbound']:.1f} 亿")
    else:
        note = breadth.get("note", "")
        console.print(f"  [dim]{note}[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@click.group()
def review() -> None:
    """📊 Market Review — daily market summary."""
    pass


@review.command("daily")
@click.option(
    "--mode",
    type=click.Choice(["auto", "intraday", "close"]),
    default="auto",
    help="Review mode: auto (default), intraday, or close.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output as JSON.",
)
def daily(mode: str, output_json: bool) -> None:
    """Daily market review (indices, sectors, breadth)."""
    resolved = _resolve_mode(mode)

    # Fetch data with graceful degradation
    indices = fetch_indices()
    sectors_industry = fetch_sector_board("industry")
    sectors_concept = fetch_sector_board("concept")
    breadth = fetch_market_breadth()

    if output_json:
        click.echo(
            render_json(indices, sectors_industry, sectors_concept, breadth, resolved)
        )
        return

    _print_rich_review(indices, sectors_industry, sectors_concept, breadth, resolved)
