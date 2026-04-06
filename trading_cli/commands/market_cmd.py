"""Multi-market commands — market info, FX rates, and cross-market views."""

from __future__ import annotations

from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading_cli.core.market import (
    MARKETS,
    Currency,
    get_market,
    detect_market,
    fx_rate,
    convert_currency,
    normalize_symbol,
)
from trading_cli.core.data_source import DataFetchRequest, registry
from trading_cli.core.ib_provider import IBProvider
from trading_cli.core.config import get_config
from trading_cli.core.tushare_provider import TushareProvider

console = Console()


def _ensure_all_providers() -> None:
    """Register both Tushare and IB providers."""
    providers = registry.list_providers()
    if "tushare" not in providers:
        config = get_config()
        registry.register(TushareProvider(config.data.tushare))
    if "ib" not in providers:
        registry.register(IBProvider(simulated=True))


@click.group()
def market():
    """🌍 Multi-Market — cross-market data, FX rates, and market info."""
    pass


@market.command("info")
@click.argument("market_code", default="all")
def market_info(market_code: str):
    """Show market information and trading hours.

    Examples:

        trading-cli market info

        trading-cli market info US
    """
    codes = (
        list(MARKETS.keys()) if market_code.lower() == "all" else [market_code.upper()]
    )

    for code in codes:
        try:
            m = get_market(code)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            continue

        info = Table(show_header=False, box=None)
        info.add_column("k", style="dim", width=16)
        info.add_column("v")
        info.add_row("Market", f"[bold]{m.name}[/bold] ({m.code})")
        info.add_row("Currency", m.currency.value)
        info.add_row("Timezone", m.timezone_name)
        info.add_row("Lot Size", str(m.lot_size))
        info.add_row("Tick Size", str(m.tick_size))
        info.add_row("Exchanges", ", ".join(m.exchange_names))

        sessions = "\n".join(
            f"  {s.label}: {s.open.strftime('%H:%M')} — {s.close.strftime('%H:%M')}"
            for s in m.sessions
        )
        info.add_row("Sessions", sessions)

        console.print(
            Panel(info, title=f"[cyan]{m.code}[/cyan] Market", border_style="blue")
        )
    console.print()


@market.command()
@click.option("--amount", "-a", type=float, default=10000, help="Amount to convert.")
@click.option(
    "--from", "from_ccy", type=click.Choice(["CNY", "USD", "HKD"]), default="USD"
)
@click.option("--to", "to_ccy", type=click.Choice(["CNY", "USD", "HKD"]), default="CNY")
def fx(amount: float, from_ccy: str, to_ccy: str):
    """Show FX rates and convert currencies.

    Examples:

        trading-cli market fx

        trading-cli market fx --amount 50000 --from USD --to CNY
    """
    # Show all rates
    table = Table(title="FX Rates")
    table.add_column("From", style="cyan")
    table.add_column("To", style="cyan")
    table.add_column("Rate", justify="right")

    for f_c in ["USD", "CNY", "HKD"]:
        for t_c in ["USD", "CNY", "HKD"]:
            if f_c != t_c:
                r = fx_rate(f_c, t_c)
                table.add_row(f_c, t_c, f"{r:.4f}")

    console.print(table)

    # Conversion
    result = convert_currency(amount, from_ccy, to_ccy)
    rate = fx_rate(from_ccy, to_ccy)
    console.print(
        f"\n  [bold]{from_ccy} {amount:,.2f}[/bold] → "
        f"[bold green]{to_ccy} {result:,.2f}[/bold green] "
        f"(rate: {rate:.4f})\n"
    )


@market.command()
@click.argument("symbols", nargs=-1, required=True)
@click.option("--days", "-d", type=int, default=30, help="Lookback days.")
@click.option(
    "--base-currency",
    "-c",
    type=click.Choice(["CNY", "USD", "HKD"]),
    default="CNY",
    help="Convert all values to this currency.",
)
def compare(symbols: tuple[str, ...], days: int, base_currency: str):
    """Compare stocks across markets in a unified view.

    Examples:

        trading-cli market compare 000001.SZ AAPL 0700.HK

        trading-cli market compare 600519 MSFT 9988.HK --base-currency USD
    """
    _ensure_all_providers()

    table = Table(
        title=f"Cross-Market Comparison (in {base_currency})", show_lines=True
    )
    table.add_column("Symbol", style="cyan bold")
    table.add_column("Market")
    table.add_column("Price", justify="right")
    table.add_column(f"Price ({base_currency})", justify="right", style="bold")
    table.add_column("Chg%", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("Provider", style="dim")

    for sym in symbols:
        mkt = detect_market(sym)
        market_info = get_market(mkt)
        provider_name = "tushare" if mkt == "CN" else "ib"

        try:
            dp = registry.get(provider_name)
        except ValueError:
            table.add_row(sym, mkt, "[red]N/A[/red]", "-", "-", "-", "missing")
            continue

        from trading_cli.core.data_source import Market as MktEnum

        request = DataFetchRequest(
            symbol=normalize_symbol(sym, mkt),
            start_date=date.today() - timedelta(days=days),
            end_date=date.today(),
            market=MktEnum(mkt),
        )

        try:
            result = dp.fetch_stock_daily(request)
        except Exception:
            table.add_row(sym, mkt, "[red]Error[/red]", "-", "-", "-", provider_name)
            continue

        if result.is_empty or len(result.data) < 2:
            table.add_row(
                sym, mkt, "[yellow]N/A[/yellow]", "-", "-", "-", provider_name
            )
            continue

        df = result.data
        close = float(df.iloc[-1]["close"])
        prev = float(df.iloc[-2]["close"])
        chg = (close - prev) / prev * 100
        vol = float(df.iloc[-1]["vol"])

        # Convert to base currency
        local_ccy = market_info.currency.value
        converted = convert_currency(close, local_ccy, base_currency)

        chg_c = "green" if chg >= 0 else "red"
        table.add_row(
            normalize_symbol(sym, mkt),
            mkt,
            f"{local_ccy} {close:,.2f}",
            f"{base_currency} {converted:,.2f}",
            f"[{chg_c}]{chg:+.2f}%[/{chg_c}]",
            f"{vol:,.0f}",
            provider_name,
        )

    console.print()
    console.print(table)
    console.print()
