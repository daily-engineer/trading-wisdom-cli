"""Technical analysis commands."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import click
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from trading_cli.core.config import get_config
from trading_cli.core.data_source import DataFetchRequest, Market, registry
from trading_cli.core.tushare_provider import TushareProvider
from trading_cli.core.indicators import TechnicalIndicators

console = Console()


def _ensure_provider():
    """Ensure data provider is registered."""
    if not registry.list_providers():
        config = get_config()
        provider = TushareProvider(config.data.tushare)
        registry.register(provider)


def _fetch_data(symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
    """Fetch stock data for analysis."""
    _ensure_provider()
    config = get_config()
    dp = registry.get(config.data.default_provider)

    request = DataFetchRequest(
        symbol=symbol,
        start_date=date.today() - timedelta(days=days),
        end_date=date.today(),
        market=Market.CN,
    )

    try:
        result = dp.fetch_stock_daily(request)
        return result.data
    except Exception as e:
        console.print(f"[red]Failed to fetch data: {e}[/red]")
        return None


def _get_signal(
    rsi: float, macd_hist: float, price: float, bb_upper: float, bb_lower: float
) -> list[tuple[str, str, str]]:
    """Generate trading signal based on indicators."""
    signals = []

    # RSI signals
    if rsi < 30:
        signals.append(("RSI", "OVERSOLD", "green"))
    elif rsi > 70:
        signals.append(("RSI", "OVERBOUGHT", "red"))
    else:
        signals.append(("RSI", "NEUTRAL", "yellow"))

    # Bollinger Bands signals
    bb_position = (
        (price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
    )
    if bb_position < 0.2:
        signals.append(("BB", "NEAR_LOWER", "green"))
    elif bb_position > 0.8:
        signals.append(("BB", "NEAR_UPPER", "red"))
    else:
        signals.append(("BB", "MIDDLE", "yellow"))

    # MACD signals
    if macd_hist > 0:
        signals.append(("MACD", "BULLISH", "green"))
    else:
        signals.append(("MACD", "BEARISH", "red"))

    return signals


@click.group()
def analyze():
    """🤖 AI Analysis — technical indicators and signals."""
    pass


@analyze.command()
@click.argument("symbol")
@click.option(
    "--days", "-d", type=int, default=60, help="Days of historical data (default: 60)"
)
@click.option(
    "--limit", "-l", type=int, default=10, help="Rows to display (default: 10)"
)
def indicators(symbol: str, days: int, limit: int):
    """Calculate and display technical indicators.

    Examples:

        trading-cli analyze indicators 000001.SZ

        trading-cli analyze indicators 600519 --days 120
    """
    console.print(f"\n[cyan]📊 Technical Analysis:[/cyan] {symbol}")

    df = _fetch_data(symbol, days)
    if df is None or df.empty:
        console.print("[yellow]No data available for analysis.[/yellow]")
        return

    # Calculate indicators
    df_with_indicators = TechnicalIndicators.all_indicators(df)

    # Display summary
    latest = df_with_indicators.iloc[-1]

    # Key metrics table
    table = Table(title=f"Technical Indicators - {symbol}", show_lines=False)
    table.add_column("Indicator", style="cyan", justify="left")
    table.add_column("Value", style="white", justify="right")
    table.add_column("Signal", style="white", justify="center")

    # RSI
    rsi_val = latest.get("rsi_14", 0)
    if pd.isna(rsi_val):
        rsi_signal = "[yellow]N/A[/yellow]"
    elif rsi_val < 30:
        rsi_signal = "[green]Oversold[/green]"
    elif rsi_val > 70:
        rsi_signal = "[red]Overbought[/red]"
    else:
        rsi_signal = "[yellow]Neutral[/yellow]"
    table.add_row("RSI (14)", f"{rsi_val:.2f}", rsi_signal)

    # MACD
    macd_val = latest.get("macd", 0)
    macd_sig = latest.get("macd_signal", 0)
    if pd.isna(macd_val):
        macd_str = "N/A"
    else:
        macd_str = f"{macd_val:.4f} (signal: {macd_sig:.4f})"
    table.add_row("MACD", macd_str, "")

    # Moving Averages
    price = latest.get("close", 0)
    for period in [5, 20, 60]:
        ma = latest.get(f"ema_{period}", 0)
        if pd.isna(ma):
            continue
        trend = "▲" if price > ma else "▼"
        table.add_row(f"EMA ({period})", f"{ma:.2f}", f"[cyan]{trend}[/cyan]")

    # Bollinger Bands
    bb_upper = latest.get("bb_upper", 0)
    bb_lower = latest.get("bb_lower", 0)
    if not pd.isna(bb_upper):
        bb_pct = (
            (price - bb_lower) / (bb_upper - bb_lower) * 100
            if bb_upper != bb_lower
            else 50
        )
        table.add_row("BBands", f"{bb_lower:.2f} - {bb_upper:.2f}", f"{bb_pct:.0f}% up")

    console.print(table)

    # Recent data with indicators
    console.print(f"\n[cyan]Recent Data with Indicators:[/cyan]")
    display_cols = ["trade_date", "close", "vol", "rsi_14", "macd", "macd_hist"]
    available_cols = [c for c in display_cols if c in df_with_indicators.columns]

    data_table = Table(show_lines=True)
    for col in available_cols:
        data_table.add_column(col.replace("_", " ").title(), justify="right")

    for _, row in df_with_indicators.tail(limit).iterrows():
        values = []
        for col in available_cols:
            val = row[col]
            if col == "trade_date":
                val_str = str(val.date()) if hasattr(val, "date") else str(val)
            elif col == "vol":
                val_str = f"{val:,.0f}"
            elif col == "rsi_14":
                val_str = f"{val:.1f}" if not pd.isna(val) else "N/A"
            else:
                val_str = f"{val:.2f}" if not pd.isna(val) else "N/A"
            values.append(val_str)
        data_table.add_row(*values)

    console.print(data_table)


@analyze.command()
@click.argument("symbol")
@click.option(
    "--days", "-d", type=int, default=60, help="Days of historical data (default: 60)"
)
def signal(symbol: str, days: int):
    """Get trading signals for a symbol.

    Examples:

        trading-cli analyze signal 000001.SZ
    """
    console.print(f"\n[cyan]📈 Trading Signal:[/cyan] {symbol}\n")

    df = _fetch_data(symbol, days)
    if df is None or df.empty:
        console.print("[yellow]No data available for analysis.[/yellow]")
        return

    df_with_indicators = TechnicalIndicators.all_indicators(df)
    latest = df_with_indicators.iloc[-1]

    price = latest.get("close", 0)
    rsi = latest.get("rsi_14", 50)
    macd_hist = latest.get("macd_hist", 0)
    bb_upper = latest.get("bb_upper", 0)
    bb_lower = latest.get("bb_lower", 0)
    ema_20 = latest.get("ema_20", 0)
    ema_60 = latest.get("ema_60", 0)
    stoch_k = latest.get("stoch_k", 50)

    # Build signal summary
    signals = []

    # Trend signals
    if not pd.isna(ema_20) and not pd.isna(ema_60):
        if ema_20 > ema_60:
            signals.append(("Trend", "📈 BULLISH (EMA Golden Cross)", "green"))
        else:
            signals.append(("Trend", "📉 BEARISH (EMA Death Cross)", "red"))

    # RSI signals
    if pd.isna(rsi):
        signals.append(("RSI (14)", "⚪ N/A", "white"))
    elif rsi < 30:
        signals.append(("RSI (14)", "🟢 OVERSOLD", "green"))
    elif rsi > 70:
        signals.append(("RSI (14)", "🔴 OVERBOUGHT", "red"))
    else:
        signals.append(("RSI (14)", f"🟡 NEUTRAL ({rsi:.1f})", "yellow"))

    # MACD signals
    if pd.isna(macd_hist):
        signals.append(("MACD", "⚪ N/A", "white"))
    elif macd_hist > 0:
        signals.append(("MACD", "🟢 BULLISH CROSS", "green"))
    else:
        signals.append(("MACD", "🔴 BEARISH CROSS", "red"))

    # Bollinger Bands signals
    if not pd.isna(bb_upper) and not pd.isna(bb_lower):
        bb_pos = (price - bb_lower) / (bb_upper - bb_lower)
        if bb_pos < 0.2:
            signals.append(("Bollinger", "🟢 NEAR LOWER BAND", "green"))
        elif bb_pos > 0.8:
            signals.append(("Bollinger", "🔴 NEAR UPPER BAND", "red"))
        else:
            signals.append(("Bollinger", f"🟡 MIDDLE ({bb_pos*100:.0f}%)", "yellow"))

    # Stochastic
    if pd.isna(stoch_k):
        signals.append(("Stochastic", "⚪ N/A", "white"))
    elif stoch_k < 20:
        signals.append(("Stochastic", "🟢 OVERSOLD", "green"))
    elif stoch_k > 80:
        signals.append(("Stochastic", "🔴 OVERBOUGHT", "red"))
    else:
        signals.append(("Stochastic", f"🟡 NEUTRAL ({stoch_k:.0f})", "yellow"))

    # Display signals
    table = Table(show_lines=False, box=None)
    table.add_column("Indicator", style="cyan", width=15)
    table.add_column("Signal", justify="left")

    for _, sig, color in signals:
        table.add_row(_, f"[{color}]{sig}[/{color}]")

    console.print(table)

    # Overall summary
    bullish_count = sum(1 for _, _, c in signals if c == "green")
    bearish_count = sum(1 for _, _, c in signals if c == "red")

    console.print(f"\n[white]Current Price:[/white] [cyan]{price:.2f}[/cyan]")

    if bullish_count > bearish_count + 1:
        overall = "[green]🟢 BULLISH BIAS[/green]"
    elif bearish_count > bullish_count + 1:
        overall = "[red]🔴 BEARISH BIAS[/red]"
    else:
        overall = "[yellow]🟡 NEUTRAL[/yellow]"

    console.print(f"[white]Overall:[/white] {overall}")


@analyze.command()
@click.argument("symbol")
@click.option(
    "--period", "-p", type=int, default=20, help="Lookback period (default: 20)"
)
def summary(symbol: str, period: int):
    """Display a quick technical summary.

    Examples:

        trading-cli analyze summary 000001.SZ
    """
    df = _fetch_data(symbol, period * 3)
    if df is None or df.empty:
        console.print("[yellow]No data available.[/yellow]")
        return

    df_with_indicators = TechnicalIndicators.all_indicators(df)
    latest = df_with_indicators.tail(period)

    # Calculate summary stats
    price = latest["close"].iloc[-1]
    price_change = ((price - latest["close"].iloc[0]) / latest["close"].iloc[0]) * 100

    rsi = latest["rsi_14"].iloc[-1]
    avg_rsi = latest["rsi_14"].mean()

    content = Text()
    content.append(f"Price: ", style="white")
    content.append(
        f"{price:.2f} ({price_change:+.2f}%)\n",
        style="green" if price_change > 0 else "red",
    )
    content.append(f"RSI(14): ", style="white")
    content.append(f"{rsi:.1f} (avg: {avg_rsi:.1f})\n", style="yellow")

    panel = Panel(content, title=f"📊 {symbol} Summary", border_style="cyan")
    console.print(panel)
