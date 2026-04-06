"""Trading execution commands — paper trading with risk management."""

from __future__ import annotations

from datetime import date, timedelta

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, Market, registry
from trading_cli.core.tushare_provider import TushareProvider
from trading_cli.core.order import OrderSide, OrderType
from trading_cli.core.paper_trader import PaperTrader

console = Console()

# Session-level paper trader
_trader: PaperTrader | None = None


def _get_trader() -> PaperTrader:
    global _trader
    if _trader is None:
        _trader = PaperTrader()
    return _trader


def _ensure_providers() -> None:
    if not registry.list_providers():
        config = get_config()
        registry.register(TushareProvider(config.data.tushare))


def _fetch_price(symbol: str) -> float | None:
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
def order_buy(symbol: str, qty: int, price: float | None):
    """Place a buy order.

    Examples:

        trading-cli trade order buy 000001.SZ --qty 1000

        trading-cli trade order buy 600519 --qty 100 --price 1700
    """
    trader = _get_trader()
    current_price = price or _fetch_price(symbol)
    if current_price is None:
        console.print(f"[red]Cannot determine price for {symbol}.[/red]")
        return

    order_type = OrderType.LIMIT if price else OrderType.MARKET
    result = trader.place_order(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        order_type=order_type,
        price=price,
        current_price=current_price,
    )

    if result.status.value == "FILLED":
        console.print(
            f"[green]✓ BUY FILLED[/green] {symbol} × {qty} @ ¥{result.filled_price:.2f}"
        )
        console.print(
            f"  Commission: ¥{result.commission:.2f} | Cash remaining: ¥{trader.account.cash:,.2f}"
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
def order_sell(symbol: str, qty: int, price: float | None):
    """Place a sell order.

    Examples:

        trading-cli trade order sell 000001.SZ --qty 500

        trading-cli trade order sell 600519  (closes entire position)
    """
    trader = _get_trader()
    current_price = price or _fetch_price(symbol)
    if current_price is None:
        console.print(f"[red]Cannot determine price for {symbol}.[/red]")
        return

    # Default: close entire position
    if qty == 0:
        pos = trader.account.positions.get(symbol.upper())
        if not pos:
            console.print(f"[yellow]No position in {symbol} to sell.[/yellow]")
            return
        qty = pos.quantity

    result = trader.place_order(
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=qty,
        order_type=OrderType.LIMIT if price else OrderType.MARKET,
        price=price,
        current_price=current_price,
    )

    if result.status.value == "FILLED":
        console.print(
            f"[green]✓ SELL FILLED[/green] {symbol} × {qty} @ ¥{result.filled_price:.2f}"
        )
        console.print(
            f"  Commission: ¥{result.commission:.2f} | Cash: ¥{trader.account.cash:,.2f}"
        )
    elif result.status.value == "REJECTED":
        console.print(f"[red]✗ REJECTED:[/red] {result.message}")


@order.command("list")
@click.option(
    "--status",
    "-s",
    type=click.Choice(["all", "open", "filled", "cancelled"]),
    default="all",
)
def order_list(status: str):
    """List orders."""
    trader = _get_trader()
    orders = trader.account.orders

    if status == "open":
        orders = trader.account.get_open_orders()
    elif status == "filled":
        orders = trader.account.get_filled_orders()
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
            f"¥{o.filled_price:.2f}"
            if o.filled_price
            else (f"¥{o.price:.2f}" if o.price else "MKT")
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
    trader = _get_trader()
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
    trader = _get_trader()
    positions = trader.account.positions

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
            f"¥{p.avg_cost:.2f}",
            f"¥{p.current_price:.2f}",
            f"¥{p.market_value:,.2f}",
            f"[{c}]¥{p.unrealized_pnl:,.2f}[/{c}]",
            f"[{c}]{p.unrealized_pnl_pct:+.2f}%[/{c}]",
        )
    console.print(table)


@position.command("close")
@click.argument("symbol")
def position_close(symbol: str):
    """Close an entire position at market price."""
    trader = _get_trader()
    current_price = _fetch_price(symbol)
    if current_price is None:
        console.print(f"[red]Cannot determine price for {symbol}.[/red]")
        return

    order = trader.close_position(symbol, current_price)
    if order is None:
        console.print(f"[yellow]No position in {symbol}.[/yellow]")
    elif order.status.value == "FILLED":
        console.print(
            f"[green]✓ Position closed[/green] {symbol} × {order.filled_quantity} @ ¥{order.filled_price:.2f}"
        )
    else:
        console.print(f"[red]Close failed:[/red] {order.message}")


# ---- account ----


@trade.command()
def account():
    """Show account summary."""
    trader = _get_trader()
    a = trader.account

    pnl_c = "green" if a.total_pnl >= 0 else "red"
    info = Table(show_header=False, box=None)
    info.add_column("k", style="dim", width=18)
    info.add_column("v", justify="right")
    info.add_row("Account ID", a.account_id)
    info.add_row("Initial Capital", f"¥{a.initial_capital:,.2f}")
    info.add_row("Cash", f"¥{a.cash:,.2f}")
    info.add_row("Market Value", f"¥{a.total_market_value:,.2f}")
    info.add_row("Total Equity", f"[bold]¥{a.total_equity:,.2f}[/bold]")
    info.add_row(
        "P&L", f"[{pnl_c}]¥{a.total_pnl:,.2f} ({a.total_pnl_pct:+.2f}%)[/{pnl_c}]"
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
    trader = _get_trader()
    result = trader.check_risk()

    if result.passed:
        console.print("[green]✓ All risk checks passed.[/green]")
    else:
        console.print("[red]⚠ Risk violations detected:[/red]")
        for v in result.violations:
            console.print(f"  [red]•[/red] {v}")

    # Show risk limits
    rc = trader.risk_engine.config
    console.print(
        f"\n[dim]Risk limits: max position {rc.max_position_pct:.0%} | "
        f"max positions {rc.max_positions} | "
        f"stop loss {rc.max_single_loss_pct}% | "
        f"daily loss limit {rc.max_daily_loss_pct}% | "
        f"cash reserve {rc.min_cash_reserve_pct:.0%}[/dim]"
    )
