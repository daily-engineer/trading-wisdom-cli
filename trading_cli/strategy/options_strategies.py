"""Options trading strategies and payoff simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np

from trading_cli.core.options import BlackScholes, OptionType


@dataclass
class OptionLeg:
    """A single leg of an options strategy."""

    option_type: OptionType
    strike: float
    side: int  # +1 = long, -1 = short (written)
    premium: float  # per-unit premium paid (+) or received (-)
    quantity: int = 1


@dataclass
class StrategyPayoff:
    """Payoff profile for an options strategy."""

    name: str
    legs: list[OptionLeg]
    underlying_price: float
    net_premium: float  # total net premium (negative = net credit)
    max_profit: float
    max_loss: float
    break_evens: list[float]
    prices: list[float] = field(default_factory=list)
    payoffs: list[float] = field(default_factory=list)

    @property
    def risk_reward_ratio(self) -> float:
        return (
            abs(self.max_profit / self.max_loss) if self.max_loss != 0 else float("inf")
        )


def _payoff_at_expiry(legs: list[OptionLeg], price: float) -> float:
    """Calculate net payoff at expiry for a given underlying price."""
    total = 0.0
    for leg in legs:
        if leg.option_type == OptionType.CALL:
            intrinsic = max(price - leg.strike, 0)
        else:
            intrinsic = max(leg.strike - price, 0)
        total += (intrinsic - leg.premium) * leg.side * leg.quantity
    return total


def _analyze_payoff(
    name: str, legs: list[OptionLeg], underlying_price: float, price_range: float = 0.3
) -> StrategyPayoff:
    """Compute full payoff profile across a price range."""
    low = underlying_price * (1 - price_range)
    high = underlying_price * (1 + price_range)
    prices = np.linspace(low, high, 200).tolist()
    payoffs = [_payoff_at_expiry(legs, p) for p in prices]

    net_premium = sum(leg.premium * leg.side * leg.quantity for leg in legs)

    # Find break-evens (sign changes)
    break_evens = []
    for i in range(1, len(payoffs)):
        if payoffs[i - 1] * payoffs[i] < 0:
            # Linear interpolation
            p1, p2 = prices[i - 1], prices[i]
            v1, v2 = payoffs[i - 1], payoffs[i]
            be = p1 - v1 * (p2 - p1) / (v2 - v1)
            break_evens.append(round(be, 4))

    return StrategyPayoff(
        name=name,
        legs=legs,
        underlying_price=underlying_price,
        net_premium=round(net_premium, 4),
        max_profit=round(max(payoffs), 4),
        max_loss=round(min(payoffs), 4),
        break_evens=break_evens,
        prices=prices,
        payoffs=payoffs,
    )


# ---------------------------------------------------------------------------
# Pre-built strategy constructors
# ---------------------------------------------------------------------------


def covered_call(
    underlying_price: float, call_strike: float, call_premium: float
) -> StrategyPayoff:
    """Covered call: long stock + short call."""
    legs = [
        OptionLeg(
            OptionType.CALL, strike=0, side=+1, premium=underlying_price
        ),  # proxy for stock
        OptionLeg(OptionType.CALL, strike=call_strike, side=-1, premium=call_premium),
    ]
    # For covered call, adjust payoff manually
    prices = np.linspace(underlying_price * 0.7, underlying_price * 1.3, 200).tolist()
    payoffs = []
    for p in prices:
        stock_pnl = p - underlying_price
        short_call = call_premium - max(p - call_strike, 0)
        payoffs.append(stock_pnl + short_call)

    max_profit = call_premium + (call_strike - underlying_price)
    max_loss = -(underlying_price - call_premium)  # stock goes to 0
    be = underlying_price - call_premium

    return StrategyPayoff(
        name="Covered Call",
        legs=legs,
        underlying_price=underlying_price,
        net_premium=round(-call_premium, 4),
        max_profit=round(max_profit, 4),
        max_loss=round(max_loss, 4),
        break_evens=[round(be, 4)],
        prices=prices,
        payoffs=payoffs,
    )


def protective_put(
    underlying_price: float, put_strike: float, put_premium: float
) -> StrategyPayoff:
    """Protective put: long stock + long put."""
    prices = np.linspace(underlying_price * 0.7, underlying_price * 1.3, 200).tolist()
    payoffs = []
    for p in prices:
        stock_pnl = p - underlying_price
        long_put = max(put_strike - p, 0) - put_premium
        payoffs.append(stock_pnl + long_put)

    max_loss = -(underlying_price - put_strike + put_premium)
    be = underlying_price + put_premium

    return StrategyPayoff(
        name="Protective Put",
        legs=[
            OptionLeg(OptionType.PUT, strike=0, side=+1, premium=underlying_price),
            OptionLeg(OptionType.PUT, strike=put_strike, side=+1, premium=put_premium),
        ],
        underlying_price=underlying_price,
        net_premium=round(put_premium, 4),
        max_profit=round(max(payoffs), 4),
        max_loss=round(max_loss, 4),
        break_evens=[round(be, 4)],
        prices=prices,
        payoffs=payoffs,
    )


def bull_call_spread(
    underlying_price: float,
    long_strike: float,
    long_premium: float,
    short_strike: float,
    short_premium: float,
) -> StrategyPayoff:
    """Bull call spread: long lower call + short higher call."""
    legs = [
        OptionLeg(OptionType.CALL, strike=long_strike, side=+1, premium=long_premium),
        OptionLeg(OptionType.CALL, strike=short_strike, side=-1, premium=short_premium),
    ]
    return _analyze_payoff("Bull Call Spread", legs, underlying_price)


def bear_put_spread(
    underlying_price: float,
    long_strike: float,
    long_premium: float,
    short_strike: float,
    short_premium: float,
) -> StrategyPayoff:
    """Bear put spread: long higher put + short lower put."""
    legs = [
        OptionLeg(OptionType.PUT, strike=long_strike, side=+1, premium=long_premium),
        OptionLeg(OptionType.PUT, strike=short_strike, side=-1, premium=short_premium),
    ]
    return _analyze_payoff("Bear Put Spread", legs, underlying_price)


def iron_condor(
    underlying_price: float,
    put_long_strike: float,
    put_long_premium: float,
    put_short_strike: float,
    put_short_premium: float,
    call_short_strike: float,
    call_short_premium: float,
    call_long_strike: float,
    call_long_premium: float,
) -> StrategyPayoff:
    """Iron condor: bull put spread + bear call spread."""
    legs = [
        OptionLeg(
            OptionType.PUT, strike=put_long_strike, side=+1, premium=put_long_premium
        ),
        OptionLeg(
            OptionType.PUT, strike=put_short_strike, side=-1, premium=put_short_premium
        ),
        OptionLeg(
            OptionType.CALL,
            strike=call_short_strike,
            side=-1,
            premium=call_short_premium,
        ),
        OptionLeg(
            OptionType.CALL, strike=call_long_strike, side=+1, premium=call_long_premium
        ),
    ]
    return _analyze_payoff("Iron Condor", legs, underlying_price)


def straddle(
    underlying_price: float,
    strike: float,
    call_premium: float,
    put_premium: float,
    side: int = 1,
) -> StrategyPayoff:
    """Long/short straddle: call + put at same strike."""
    legs = [
        OptionLeg(OptionType.CALL, strike=strike, side=side, premium=call_premium),
        OptionLeg(OptionType.PUT, strike=strike, side=side, premium=put_premium),
    ]
    name = "Long Straddle" if side == 1 else "Short Straddle"
    return _analyze_payoff(name, legs, underlying_price)


# ---------------------------------------------------------------------------
# Options strategy backtest (simplified time-decay simulation)
# ---------------------------------------------------------------------------


@dataclass
class OptionsBacktestResult:
    """Result of an options strategy backtest."""

    strategy_name: str
    underlying_symbol: str
    entry_price: float
    exit_price: float
    days_held: int
    entry_payoff: float
    exit_payoff: float
    pnl: float
    pnl_pct: float
    greeks_at_entry: dict
    greeks_at_exit: dict


def backtest_option_strategy(
    strategy_payoff: StrategyPayoff,
    price_path: list[float],
    vol: float = 0.25,
    rate: float = 0.03,
    total_days: int = 30,
) -> OptionsBacktestResult:
    """Backtest an options strategy along a price path.

    Simulates mark-to-market using Black-Scholes at each step.
    """
    if not price_path or len(price_path) < 2:
        return OptionsBacktestResult(
            strategy_name=strategy_payoff.name,
            underlying_symbol="",
            entry_price=0,
            exit_price=0,
            days_held=0,
            entry_payoff=0,
            exit_payoff=0,
            pnl=0,
            pnl_pct=0,
            greeks_at_entry={},
            greeks_at_exit={},
        )

    n = len(price_path)
    days_per_step = max(total_days / n, 0.1)

    def _mtm(
        legs: list[OptionLeg], spot: float, days_remaining: float
    ) -> tuple[float, dict]:
        T = max(days_remaining / 365.0, 0.0001)
        total_value = 0.0
        total_delta = 0.0
        total_theta = 0.0
        for leg in legs:
            if leg.strike == 0:
                # Stock proxy
                total_value += spot * leg.side * leg.quantity
                total_delta += leg.side * leg.quantity
                continue
            p = BlackScholes.price(spot, leg.strike, T, rate, vol, leg.option_type)
            g = BlackScholes.greeks(spot, leg.strike, T, rate, vol, leg.option_type)
            total_value += p * leg.side * leg.quantity
            total_delta += g.delta * leg.side * leg.quantity
            total_theta += g.theta * leg.side * leg.quantity
        return total_value, {
            "delta": round(total_delta, 4),
            "theta": round(total_theta, 4),
        }

    entry_value, entry_greeks = _mtm(strategy_payoff.legs, price_path[0], total_days)
    exit_value, exit_greeks = _mtm(
        strategy_payoff.legs, price_path[-1], max(total_days - n * days_per_step, 0.1)
    )

    # P&L includes premium already baked into mtm
    entry_cost = sum(
        leg.premium * leg.side * leg.quantity for leg in strategy_payoff.legs
    )
    pnl = exit_value - entry_value
    pnl_pct = (pnl / abs(entry_cost) * 100) if entry_cost else 0

    return OptionsBacktestResult(
        strategy_name=strategy_payoff.name,
        underlying_symbol="",
        entry_price=price_path[0],
        exit_price=price_path[-1],
        days_held=n,
        entry_payoff=round(entry_value, 4),
        exit_payoff=round(exit_value, 4),
        pnl=round(pnl, 4),
        pnl_pct=round(pnl_pct, 2),
        greeks_at_entry=entry_greeks,
        greeks_at_exit=exit_greeks,
    )
