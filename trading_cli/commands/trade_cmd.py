"""Trading execution commands — paper and live trading with risk management."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading_cli.core.base_trader import BaseTrader
from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, registry
from trading_cli.core.tushare_provider import TushareProvider
from trading_cli.core.order import OrderSide, OrderType
from trading_cli.core.paper_trader import PaperTrader
from trading_cli.core.trade_logger import TradeLogger

console = Console()

# Session-level trader singletons
_paper_trader: Optional[PaperTrader] = None
_live_trader: Optional[BaseTrader] = None

_logger = TradeLogger()


def _get_trader(live: bool = False) -> BaseTrader:
    global _paper_trader, _live_trader
    if live:
        if _live_trader is None:
            from trading_cli.core.live_trader import RealTrader

            _live_trader = RealTrader()
        return _live_trader
    if _paper_trader is None:
        _paper_trader = PaperTrader()
    return _paper_trader


def _ensure_providers() -> None:
    if not registry.list_providers():
        config = get_config()
        registry.register(TushareProvider(config.data.tushare))


def _fetch_price(symbol: str) -> Optional[float]:
    """Fetch the latest closing price for a symbol."""
    _ensure_providers()
    config = get_config()
    dp = registry.get(config.data.default_provider)
    request = DataFetchRequest(
        symbol=symbol,
        start_date=date.today() - timedelta(days=10),
        end_date=date.today(),
    )
    try:
        result = dp.fetch_stock_daily(request)
        if not result.is_empty:
            return float(result.data.iloc[-1]["close"])
    except Exception:
        pass
    return None


def _confirm_live(symbol: str, side: str, qty: int, price: Optional[float]) -> bool:
    """Show live-order warning and prompt for confirmation. Returns True if confirmed."""
    price_str = f"@ ${price:.2f}" if price else "@ MARKET"
    console.print(f"\n[bold red]LIVE ORDER — REAL MONEY[/bold red]")
    console.print(f"  {side} {symbol} × {qty} {price_str}")
    return click.confirm("Confirm?", default=False)


@click.group()
def trade():
    """💹 Trading Execution — paper trading with risk management."""
    pass


# ---- order sub-group ----


@trade.group()
def order():
    """Manage orders."""
    pass


@order.command("buy")
@click.argument("symbol")
@click.option("--qty", "-q", type=int, required=True, help="Number of shares.")
@click.option(
    "--price",
    "-p",
    type=float,
    default=None,
    help="Limit price (omit for market order).",
)
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
@click.option(
    "--yes",
    "skip_confirm",
    is_flag=True,
    default=False,
    help="Skip confirmation (live mode only).",
)
def order_buy(
    symbol: str, qty: int, price: Optional[float], live: bool, skip_confirm: bool
):
    """Place a buy order.

    Examples:

        trading-cli trade order buy 000001.SZ --qty 1000

        trading-cli trade order buy AAPL --qty 100 --live
    """
    if live and not skip_confirm:
        if not _confirm_live(symbol, "BUY", qty, price):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    trader = _get_trader(live)
    # Fetch price after confirmation; live market orders don't require a local price
    if not live or price is not None:
        current_price = price or _fetch_price(symbol)
        if current_price is None:
            console.print(f"[red]Cannot determine price for {symbol}.[/red]")
            return
    else:
        current_price = None

    order_type = OrderType.LIMIT if price else OrderType.MARKET
    result = trader.place_order(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        order_type=order_type,
        price=price,
        current_price=current_price,
    )

    mode = "live" if live else "paper"
    if not live:
        _logger.log(result, mode=mode)

    if result.status.value == "FILLED":
        console.print(
            f"[green]✓ BUY FILLED[/green] [{mode}] {symbol} × {qty} @ ${result.filled_price:.2f}"
        )
    elif result.status.value == "REJECTED":
        console.print(f"[red]✗ REJECTED:[/red] {result.message}")
    else:
        console.print(
            f"[yellow]⏳ {result.status.value}[/yellow] Order {result.id} placed."
        )


@order.command("sell")
@click.argument("symbol")
@click.option(
    "--qty",
    "-q",
    type=int,
    default=0,
    help="Shares to sell (0 = close entire position).",
)
@click.option("--price", "-p", type=float, default=None, help="Limit price.")
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
@click.option(
    "--yes",
    "skip_confirm",
    is_flag=True,
    default=False,
    help="Skip confirmation (live mode only).",
)
def order_sell(
    symbol: str, qty: int, price: Optional[float], live: bool, skip_confirm: bool
):
    """Place a sell order.

    Examples:

        trading-cli trade order sell 000001.SZ --qty 500

        trading-cli trade order sell AAPL --live --yes
    """
    trader = _get_trader(live)

    # Default: close entire position (paper mode only)
    if qty == 0 and not live:
        paper = trader  # type: ignore[assignment]
        pos = paper.account.positions.get(symbol.upper())  # type: ignore[attr-defined]
        if not pos:
            console.print(f"[yellow]No position in {symbol} to sell.[/yellow]")
            return
        qty = pos.quantity
    elif qty == 0 and live:
        console.print(f"[red]--qty is required for live sell orders.[/red]")
        return

    if live and not skip_confirm:
        if not _confirm_live(symbol, "SELL", qty, price):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    # Fetch price after confirmation; live market orders don't require a local price
    if not live or price is not None:
        current_price = price or _fetch_price(symbol)
        if current_price is None:
            console.print(f"[red]Cannot determine price for {symbol}.[/red]")
            return
    else:
        current_price = None

    result = trader.place_order(
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=qty,
        order_type=OrderType.LIMIT if price else OrderType.MARKET,
        price=price,
        current_price=current_price,
    )

    mode = "live" if live else "paper"
    if not live:
        _logger.log(result, mode=mode)

    if result.status.value == "FILLED":
        console.print(
            f"[green]✓ SELL FILLED[/green] [{mode}] {symbol} × {qty} @ ${result.filled_price:.2f}"
        )
    elif result.status.value == "REJECTED":
        console.print(f"[red]✗ REJECTED:[/red] {result.message}")
    else:
        console.print(
            f"[yellow]⏳ {result.status.value}[/yellow] Order {result.id} placed."
        )


@order.command("list")
@click.option(
    "--status",
    "-s",
    type=click.Choice(["all", "open", "filled", "cancelled"]),
    default="all",
)
def order_list(status: str):
    """List orders."""
    trader = _get_trader(live=False)
    paper = trader  # type: ignore[assignment]
    orders = paper.account.orders  # type: ignore[attr-defined]

    if status == "open":
        orders = paper.account.get_open_orders()  # type: ignore[attr-defined]
    elif status == "filled":
        orders = paper.account.get_filled_orders()  # type: ignore[attr-defined]
    elif status == "cancelled":
        orders = [o for o in orders if o.status.value == "CANCELLED"]

    if not orders:
        console.print("[yellow]No orders.[/yellow]")
        return

    table = Table(title="Orders")
    table.add_column("ID", style="cyan")
    table.add_column("Symbol", style="bold")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Status")
    table.add_column("Time", style="dim")

    for o in orders:
        side_c = "green" if o.side == OrderSide.BUY else "red"
        status_c = {
            "FILLED": "green",
            "REJECTED": "red",
            "CANCELLED": "dim",
            "PENDING": "yellow",
        }.get(o.status.value, "white")
        p = (
            f"${o.filled_price:.2f}"
            if o.filled_price
            else (f"${o.price:.2f}" if o.price else "MKT")
        )
        table.add_row(
            o.id,
            o.symbol,
            f"[{side_c}]{o.side.value}[/{side_c}]",
            str(o.quantity),
            p,
            f"[{status_c}]{o.status.value}[/{status_c}]",
            o.created_at.strftime("%H:%M:%S"),
        )
    console.print(table)


@order.command("cancel")
@click.argument("order_id")
def order_cancel(order_id: str):
    """Cancel a pending order."""
    trader = _get_trader(live=False)
    if trader.cancel_order(order_id):
        console.print(f"[green]✓[/green] Order {order_id} cancelled.")
    else:
        console.print(f"[red]Order {order_id} not found or not cancellable.[/red]")


# ---- position sub-group ----


@trade.group()
def position():
    """Manage positions."""
    pass


@position.command("list")
def position_list():
    """List all open positions."""
    trader = _get_trader(live=False)
    paper = trader  # type: ignore[assignment]
    positions = paper.account.positions  # type: ignore[attr-defined]

    if not positions:
        console.print("[yellow]No open positions.[/yellow]")
        return

    table = Table(title="Open Positions", show_lines=True)
    table.add_column("Symbol", style="cyan bold")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Mkt Value", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("P&L%", justify="right")

    for sym, p in positions.items():
        c = "green" if p.unrealized_pnl >= 0 else "red"
        table.add_row(
            sym,
            f"{p.quantity:,}",
            f"${p.avg_cost:.2f}",
            f"${p.current_price:.2f}",
            f"${p.market_value:,.2f}",
            f"[{c}]${p.unrealized_pnl:,.2f}[/{c}]",
            f"[{c}]{p.unrealized_pnl_pct:+.2f}%[/{c}]",
        )
    console.print(table)


@position.command("close")
@click.argument("symbol")
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
@click.option(
    "--yes", "skip_confirm", is_flag=True, default=False, help="Skip confirmation."
)
def position_close(symbol: str, live: bool, skip_confirm: bool):
    """Close an entire position at market price."""
    if live and not skip_confirm:
        if not _confirm_live(symbol, "SELL (close)", 0, None):
            console.print("[yellow]Cancelled.[/yellow]")
            return

    trader = _get_trader(live)
    current_price = _fetch_price(symbol)
    if current_price is None:
        console.print(f"[red]Cannot determine price for {symbol}.[/red]")
        return

    result = trader.close_position(symbol, current_price)
    if result is None:
        console.print(f"[yellow]No position in {symbol}.[/yellow]")
        return

    mode = "live" if live else "paper"
    if not live:
        _logger.log(result, mode=mode)

    if result.status.value == "FILLED":
        console.print(
            f"[green]✓ Position closed[/green] {symbol} × {result.filled_quantity} @ ${result.filled_price:.2f}"
        )
    else:
        console.print(f"[red]Close failed:[/red] {result.message}")


# ---- account ----


@trade.command()
def account():
    """Show account summary."""
    trader = _get_trader(live=False)
    paper = trader  # type: ignore[assignment]
    a = paper.account  # type: ignore[attr-defined]

    pnl_c = "green" if a.total_pnl >= 0 else "red"
    info = Table(show_header=False, box=None)
    info.add_column("k", style="dim", width=18)
    info.add_column("v", justify="right")
    info.add_row("Account ID", a.account_id)
    info.add_row("Initial Capital", f"${a.initial_capital:,.2f}")
    info.add_row("Cash", f"${a.cash:,.2f}")
    info.add_row("Market Value", f"${a.total_market_value:,.2f}")
    info.add_row("Total Equity", f"[bold]${a.total_equity:,.2f}[/bold]")
    info.add_row(
        "P&L", f"[{pnl_c}]${a.total_pnl:,.2f} ({a.total_pnl_pct:+.2f}%)[/{pnl_c}]"
    )
    info.add_row("Open Positions", str(a.position_count))
    info.add_row("Total Orders", str(len(a.orders)))

    console.print()
    console.print(
        Panel(info, title="[bold]Paper Trading Account[/bold]", border_style="blue")
    )
    console.print()


# ---- risk ----


@trade.command()
def risk():
    """Run portfolio risk check."""
    trader = _get_trader(live=False)
    result = trader.check_risk()

    if result.passed:
        console.print("[green]✓ All risk checks passed.[/green]")
    else:
        console.print("[red]⚠ Risk violations detected:[/red]")
        for v in result.violations:
            console.print(f"  [red]•[/red] {v}")

    paper = trader  # type: ignore[assignment]
    rc = paper.risk_engine.config  # type: ignore[attr-defined]
    console.print(
        f"\n[dim]Risk limits: max position {rc.max_position_pct:.0%} | "
        f"max positions {rc.max_positions} | "
        f"stop loss {rc.max_single_loss_pct}% | "
        f"daily loss limit {rc.max_daily_loss_pct}% | "
        f"cash reserve {rc.min_cash_reserve_pct:.0%}[/dim]"
    )


# ---- emergency sub-group ----


@trade.group()
def emergency():
    """🚨 Emergency operations."""
    pass


@emergency.command("stop")
@click.option("--live", is_flag=True, default=False, help="Use real IBKR account.")
def emergency_stop(live: bool):
    """Cancel all orders and close all positions immediately.

    This command does NOT ask for confirmation — it acts immediately.

    Examples:

        trading-cli trade emergency stop           (paper mode — safe simulation)

        trading-cli trade emergency stop --live    (REAL MONEY — acts instantly)
    """
    trader = _get_trader(live)

    if live:
        console.print("[bold red]🚨 EMERGENCY STOP — LIVE MODE — REAL MONEY[/bold red]")
    else:
        console.print("[bold yellow]🚨 Emergency Stop (paper mode)[/bold yellow]")

    # Collect prices for paper mode from current position prices
    prices: dict[str, float] = {}
    if not live:
        paper = trader  # type: ignore[assignment]
        positions = paper.account.positions  # type: ignore[attr-defined]
        for sym, pos in positions.items():
            prices[sym] = pos.current_price
        if not positions:
            console.print("[yellow]No open positions to close.[/yellow]")
            return

    orders = trader.emergency_stop(prices)

    if not orders:
        console.print("[green]✓ No positions were open.[/green]")
        return

    table = Table(title="Emergency Stop Results")
    table.add_column("Symbol", style="cyan")
    table.add_column("Qty", justify="right")
    table.add_column("Status")

    for o in orders:
        status_c = "green" if o.status.value == "FILLED" else "red"
        table.add_row(
            o.symbol, str(o.quantity), f"[{status_c}]{o.status.value}[/{status_c}]"
        )

    console.print(table)
    console.print(
        f"[green]✓ Emergency stop complete — {len(orders)} position(s) closed.[/green]"
    )
