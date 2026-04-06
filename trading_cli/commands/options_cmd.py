"""Options analysis commands — chain, greeks, pricing, payoff."""

from __future__ import annotations

from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading_cli.core.options import (
    BlackScholes,
    OptionType,
    OptionChain,
    OptionPricingResult,
    generate_option_chain,
)

console = Console()


def _parse_expiry(expiry_str: str | None, days: int) -> date:
    if expiry_str:
        return date.fromisoformat(expiry_str)
    return date.today() + timedelta(days=days)


@click.group()
def options():
    """📊 Options Analysis — pricing, Greeks, chains, and payoff diagrams."""
    pass


@options.command()
@click.argument("symbol")
@click.option("--price", "-p", type=float, required=True, help="Underlying price.")
@click.option("--expiry", "-e", default=None, help="Expiry date (YYYY-MM-DD).")
@click.option(
    "--days", "-d", type=int, default=30, help="Days to expiry if --expiry not set."
)
@click.option(
    "--vol", "-v", type=float, default=0.25, help="Base volatility (default: 0.25)."
)
@click.option(
    "--rate", "-r", type=float, default=0.03, help="Risk-free rate (default: 0.03)."
)
@click.option(
    "--strikes", "-n", type=int, default=9, help="Number of strikes (default: 9)."
)
def chain(
    symbol: str,
    price: float,
    expiry: str | None,
    days: int,
    vol: float,
    rate: float,
    strikes: int,
):
    """Display option chain with Greeks.

    Examples:

        trading-cli options chain 000001.SZ --price 11.12

        trading-cli options chain SPY --price 450 --expiry 2026-05-16 --vol 0.20
    """
    exp = _parse_expiry(expiry, days)
    oc = generate_option_chain(
        symbol, price, exp, r=rate, base_vol=vol, num_strikes=strikes
    )

    console.print(
        f"\n[cyan]Option Chain: {symbol}[/cyan] | "
        f"Spot: ¥{price:.2f} | Expiry: {exp} ({oc.calls[0].days_to_expiry}d)\n"
    )

    # Calls table
    table = Table(title="CALLS", show_lines=False)
    table.add_column("Strike", justify="right", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("IV", justify="right")
    table.add_column("Delta", justify="right", style="cyan")
    table.add_column("Gamma", justify="right")
    table.add_column("Theta", justify="right", style="red")
    table.add_column("Vega", justify="right", style="green")
    table.add_column("OI", justify="right", style="dim")

    T = oc.calls[0].time_to_expiry if oc.calls else 0
    for c in oc.calls:
        g = BlackScholes.greeks(
            price, c.strike, T, rate, c.implied_vol, OptionType.CALL
        )
        itm = "bold" if price > c.strike else ""
        table.add_row(
            f"[{itm}]{c.strike:.2f}[/{itm}]" if itm else f"{c.strike:.2f}",
            f"{c.last_price:.4f}",
            f"{c.implied_vol:.1%}",
            f"{g.delta:.3f}",
            f"{g.gamma:.4f}",
            f"{g.theta:.4f}",
            f"{g.vega:.4f}",
            f"{c.open_interest:,}",
        )
    console.print(table)

    # Puts table
    table2 = Table(title="PUTS", show_lines=False)
    table2.add_column("Strike", justify="right", style="bold")
    table2.add_column("Price", justify="right")
    table2.add_column("IV", justify="right")
    table2.add_column("Delta", justify="right", style="cyan")
    table2.add_column("Gamma", justify="right")
    table2.add_column("Theta", justify="right", style="red")
    table2.add_column("Vega", justify="right", style="green")
    table2.add_column("OI", justify="right", style="dim")

    for p in oc.puts:
        g = BlackScholes.greeks(price, p.strike, T, rate, p.implied_vol, OptionType.PUT)
        itm = "bold" if price < p.strike else ""
        table2.add_row(
            f"[{itm}]{p.strike:.2f}[/{itm}]" if itm else f"{p.strike:.2f}",
            f"{p.last_price:.4f}",
            f"{p.implied_vol:.1%}",
            f"{g.delta:.3f}",
            f"{g.gamma:.4f}",
            f"{g.theta:.4f}",
            f"{g.vega:.4f}",
            f"{p.open_interest:,}",
        )
    console.print(table2)
    console.print()


@options.command()
@click.option("--spot", "-s", type=float, required=True, help="Underlying price.")
@click.option("--strike", "-k", type=float, required=True, help="Strike price.")
@click.option("--days", "-d", type=int, default=30, help="Days to expiry.")
@click.option("--vol", "-v", type=float, default=0.25, help="Volatility.")
@click.option("--rate", "-r", type=float, default=0.03, help="Risk-free rate.")
@click.option(
    "--type", "-t", "opt_type", type=click.Choice(["call", "put"]), default="call"
)
def greeks(
    spot: float, strike: float, days: int, vol: float, rate: float, opt_type: str
):
    """Calculate Greeks for a single option.

    Examples:

        trading-cli options greeks --spot 11.12 --strike 11.0 --days 30

        trading-cli options greeks -s 450 -k 460 -d 45 -v 0.20 -t put
    """
    T = days / 365.0
    otype = OptionType.CALL if opt_type == "call" else OptionType.PUT
    result = BlackScholes.full_pricing(spot, strike, T, rate, vol, otype)
    g = result.greeks

    console.print(
        f"\n[cyan]{opt_type.upper()} Option[/cyan] | "
        f"Spot: {spot:.2f} | Strike: {strike:.2f} | "
        f"Expiry: {days}d | Vol: {vol:.1%} | {result.moneyness}\n"
    )

    info = Table(show_header=False, box=None)
    info.add_column("k", style="dim", width=20)
    info.add_column("v", justify="right")
    info.add_row("Theoretical Price", f"[bold]{result.theoretical_price:.4f}[/bold]")
    info.add_row("Intrinsic Value", f"{result.intrinsic_value:.4f}")
    info.add_row("Time Value", f"{result.time_value:.4f}")
    info.add_row("", "")
    info.add_row("Delta", f"[cyan]{g.delta:.4f}[/cyan]")
    info.add_row("Gamma", f"{g.gamma:.4f}")
    info.add_row("Theta (per day)", f"[red]{g.theta:.4f}[/red]")
    info.add_row("Vega (per 1% vol)", f"[green]{g.vega:.4f}[/green]")
    info.add_row("Rho (per 1% rate)", f"{g.rho:.4f}")

    console.print(Panel(info, title="Option Pricing & Greeks", border_style="cyan"))
    console.print()


@options.command()
@click.option("--spot", "-s", type=float, required=True, help="Underlying price.")
@click.option("--strike", "-k", type=float, required=True, help="Strike price.")
@click.option(
    "--market-price", "-m", type=float, required=True, help="Market option price."
)
@click.option("--days", "-d", type=int, default=30, help="Days to expiry.")
@click.option("--rate", "-r", type=float, default=0.03, help="Risk-free rate.")
@click.option(
    "--type", "-t", "opt_type", type=click.Choice(["call", "put"]), default="call"
)
def iv(
    spot: float,
    strike: float,
    market_price: float,
    days: int,
    rate: float,
    opt_type: str,
):
    """Calculate implied volatility from market price.

    Examples:

        trading-cli options iv --spot 11.12 --strike 11.0 --market-price 0.35 --days 30
    """
    T = days / 365.0
    otype = OptionType.CALL if opt_type == "call" else OptionType.PUT
    implied = BlackScholes.implied_volatility(
        market_price, spot, strike, T, rate, otype
    )

    console.print(f"\n[cyan]Implied Volatility:[/cyan] [bold]{implied:.2%}[/bold]")
    console.print(
        f"  {opt_type.upper()} | Spot: {spot:.2f} | Strike: {strike:.2f} | "
        f"Market: {market_price:.4f} | Days: {days}\n"
    )

    # Verify
    theo = BlackScholes.price(spot, strike, T, rate, implied, otype)
    console.print(
        f"  [dim]Verification — Theo price at IV: {theo:.4f} (market: {market_price:.4f})[/dim]\n"
    )


@options.command()
@click.option(
    "--spot", "-s", type=float, required=True, help="Current underlying price."
)
@click.option("--strike", "-k", type=float, required=True, help="Strike price.")
@click.option(
    "--premium", "-p", type=float, required=True, help="Option premium paid/received."
)
@click.option(
    "--type", "-t", "opt_type", type=click.Choice(["call", "put"]), default="call"
)
@click.option(
    "--side",
    type=click.Choice(["long", "short"]),
    default="long",
    help="Long or short.",
)
@click.option("--qty", "-q", type=int, default=1, help="Number of contracts.")
def payoff(
    spot: float, strike: float, premium: float, opt_type: str, side: str, qty: int
):
    """Display payoff analysis at various expiry prices.

    Examples:

        trading-cli options payoff -s 11.0 -k 11.0 -p 0.35 -t call --side long

        trading-cli options payoff -s 450 -k 460 -p 5.0 -t put --side short
    """
    otype = OptionType.CALL if opt_type == "call" else OptionType.PUT
    multiplier = qty * (1 if side == "long" else -1)

    # Price range: ±20% around spot
    low = spot * 0.80
    high = spot * 1.20
    step = (high - low) / 16

    console.print(
        f"\n[cyan]Payoff Analysis:[/cyan] {side.upper()} {qty} {opt_type.upper()} "
        f"| Strike: {strike:.2f} | Premium: {premium:.4f}\n"
    )

    table = Table(show_lines=False)
    table.add_column("Expiry Price", justify="right")
    table.add_column("Option Value", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("P&L%", justify="right")
    table.add_column("", width=20)

    prices = [round(low + i * step, 2) for i in range(17)]
    max_pnl: float = 0.0
    for p in prices:
        if otype == OptionType.CALL:
            intrinsic = max(p - strike, 0)
        else:
            intrinsic = max(strike - p, 0)

        pnl = (intrinsic - premium) * multiplier
        pnl_pct = (pnl / premium * 100) if premium else 0
        max_pnl = max(abs(pnl), max_pnl)

        c = "green" if pnl >= 0 else "red"
        bar_len = int(abs(pnl) / max(max_pnl, 0.01) * 10) if max_pnl else 0
        bar = ("█" * bar_len) if pnl >= 0 else ("░" * bar_len)

        table.add_row(
            f"{p:.2f}",
            f"{intrinsic:.4f}",
            f"[{c}]{pnl:+.4f}[/{c}]",
            f"[{c}]{pnl_pct:+.1f}%[/{c}]",
            f"[{c}]{bar}[/{c}]",
        )

    console.print(table)

    # Break-even
    if otype == OptionType.CALL:
        be = strike + premium if side == "long" else strike + premium
    else:
        be = strike - premium if side == "long" else strike - premium
    console.print(
        f"\n  Break-even: [bold]{be:.2f}[/bold] | Max loss: {premium * abs(multiplier):.4f}"
    )
    console.print()


@options.command("strategy")
@click.argument(
    "strategy_name",
    type=click.Choice(
        [
            "covered-call",
            "protective-put",
            "bull-spread",
            "bear-spread",
            "iron-condor",
            "straddle",
        ]
    ),
)
@click.option("--spot", "-s", type=float, required=True, help="Underlying price.")
@click.option("--vol", "-v", type=float, default=0.25, help="Volatility.")
@click.option("--days", "-d", type=int, default=30, help="Days to expiry.")
@click.option("--rate", "-r", type=float, default=0.03, help="Risk-free rate.")
def options_strategy(
    strategy_name: str, spot: float, vol: float, days: int, rate: float
):
    """Analyze a named options strategy with auto-priced legs.

    Examples:

        trading-cli options strategy covered-call --spot 11.12

        trading-cli options strategy iron-condor --spot 450 --vol 0.20

        trading-cli options strategy straddle --spot 100 --days 45
    """
    from trading_cli.strategy.options_strategies import (
        covered_call,
        protective_put,
        bull_call_spread,
        bear_put_spread,
        iron_condor,
        straddle,
    )

    T = days / 365.0
    # Auto-calculate strikes and premiums around spot
    atm = round(spot, 2)
    step = round(spot * 0.03, 2) or 1.0

    def _p(K, otype):
        return round(BlackScholes.price(spot, K, T, rate, vol, otype), 4)

    if strategy_name == "covered-call":
        k = atm + step
        result = covered_call(spot, k, _p(k, OptionType.CALL))
    elif strategy_name == "protective-put":
        k = atm - step
        result = protective_put(spot, k, _p(k, OptionType.PUT))
    elif strategy_name == "bull-spread":
        k1, k2 = atm - step, atm + step
        result = bull_call_spread(
            spot, k1, _p(k1, OptionType.CALL), k2, _p(k2, OptionType.CALL)
        )
    elif strategy_name == "bear-spread":
        k1, k2 = atm + step, atm - step
        result = bear_put_spread(
            spot, k1, _p(k1, OptionType.PUT), k2, _p(k2, OptionType.PUT)
        )
    elif strategy_name == "iron-condor":
        k_pl, k_ps, k_cs, k_cl = atm - 2 * step, atm - step, atm + step, atm + 2 * step
        result = iron_condor(
            spot,
            k_pl,
            _p(k_pl, OptionType.PUT),
            k_ps,
            _p(k_ps, OptionType.PUT),
            k_cs,
            _p(k_cs, OptionType.CALL),
            k_cl,
            _p(k_cl, OptionType.CALL),
        )
    elif strategy_name == "straddle":
        result = straddle(spot, atm, _p(atm, OptionType.CALL), _p(atm, OptionType.PUT))
    else:
        console.print(f"[red]Unknown strategy: {strategy_name}[/red]")
        return

    # Display
    console.print(
        f"\n[cyan]{result.name}[/cyan] | Spot: {spot:.2f} | "
        f"Days: {days} | Vol: {vol:.0%}\n"
    )

    info = Table(show_header=False, box=None)
    info.add_column("k", style="dim", width=20)
    info.add_column("v", justify="right")
    info.add_row(
        "Net Premium",
        f"{'¥' if result.net_premium >= 0 else '-¥'}{abs(result.net_premium):.4f}",
    )
    info.add_row("Max Profit", f"[green]{result.max_profit:+.4f}[/green]")
    info.add_row("Max Loss", f"[red]{result.max_loss:+.4f}[/red]")
    info.add_row("Risk/Reward", f"{result.risk_reward_ratio:.2f}")
    info.add_row(
        "Break-even(s)", ", ".join(f"{b:.2f}" for b in result.break_evens) or "N/A"
    )

    console.print(Panel(info, title=f"[bold]{result.name}[/bold]", border_style="cyan"))

    # Legs detail
    table = Table(title="Strategy Legs")
    table.add_column("Type", style="cyan")
    table.add_column("Strike", justify="right")
    table.add_column("Side")
    table.add_column("Premium", justify="right")

    for leg in result.legs:
        side_str = "[green]Long[/green]" if leg.side > 0 else "[red]Short[/red]"
        table.add_row(
            leg.option_type.value,
            f"{leg.strike:.2f}",
            side_str,
            f"{leg.premium:.4f}",
        )
    console.print(table)
    console.print()
