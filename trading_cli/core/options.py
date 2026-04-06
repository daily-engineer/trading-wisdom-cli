"""Options pricing engine — Black-Scholes model and Greeks calculation."""

from __future__ import annotations

import math
from datetime import date, datetime
from enum import Enum
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Standard normal helpers
# ---------------------------------------------------------------------------


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# ---------------------------------------------------------------------------
# Enums & models
# ---------------------------------------------------------------------------


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class OptionContract(BaseModel):
    """A single option contract."""

    symbol: str  # e.g. "000001.SZ"
    option_type: OptionType
    strike: float
    expiry: date
    underlying_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    last_price: float = 0.0
    volume: int = 0
    open_interest: int = 0
    implied_vol: float = 0.0

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2 if self.bid and self.ask else self.last_price

    @property
    def days_to_expiry(self) -> int:
        return max((self.expiry - date.today()).days, 0)

    @property
    def time_to_expiry(self) -> float:
        """Years to expiry."""
        return self.days_to_expiry / 365.0


class Greeks(BaseModel):
    """Option Greeks."""

    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0  # per day
    vega: float = 0.0  # per 1% vol move
    rho: float = 0.0  # per 1% rate move


class OptionPricingResult(BaseModel):
    """Complete pricing result for one option."""

    theoretical_price: float
    intrinsic_value: float
    time_value: float
    greeks: Greeks
    implied_vol: float = 0.0
    moneyness: str = ""  # ITM / ATM / OTM


class OptionChain(BaseModel):
    """A full option chain for one expiry."""

    underlying_symbol: str
    underlying_price: float
    expiry: date
    calls: list[OptionContract] = Field(default_factory=list)
    puts: list[OptionContract] = Field(default_factory=list)

    @property
    def strikes(self) -> list[float]:
        all_k = {c.strike for c in self.calls} | {p.strike for p in self.puts}
        return sorted(all_k)

    def atm_strike(self) -> float:
        """Closest strike to underlying price."""
        if not self.strikes:
            return self.underlying_price
        return min(self.strikes, key=lambda k: abs(k - self.underlying_price))


# ---------------------------------------------------------------------------
# Black-Scholes pricing engine
# ---------------------------------------------------------------------------


class BlackScholes:
    """Black-Scholes-Merton option pricing model."""

    @staticmethod
    def price(
        S: float,  # underlying price
        K: float,  # strike price
        T: float,  # time to expiry (years)
        r: float,  # risk-free rate
        sigma: float,  # volatility
        option_type: OptionType = OptionType.CALL,
    ) -> float:
        """Calculate theoretical option price."""
        if T <= 0 or sigma <= 0:
            # At/past expiry — return intrinsic value
            if option_type == OptionType.CALL:
                return max(S - K, 0)
            return max(K - S, 0)

        d1, d2 = BlackScholes._d1d2(S, K, T, r, sigma)

        if option_type == OptionType.CALL:
            return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        else:
            return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

    @staticmethod
    def greeks(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: OptionType = OptionType.CALL,
    ) -> Greeks:
        """Calculate all Greeks."""
        if T <= 0 or sigma <= 0:
            intrinsic_call = max(S - K, 0)
            delta = (
                1.0
                if (option_type == OptionType.CALL and S > K)
                else (-1.0 if (option_type == OptionType.PUT and S < K) else 0.0)
            )
            return Greeks(delta=delta)

        d1, d2 = BlackScholes._d1d2(S, K, T, r, sigma)
        sqrt_T = math.sqrt(T)
        pdf_d1 = _norm_pdf(d1)
        exp_rT = math.exp(-r * T)

        # Delta
        if option_type == OptionType.CALL:
            delta = _norm_cdf(d1)
        else:
            delta = _norm_cdf(d1) - 1.0

        # Gamma (same for call and put)
        gamma = pdf_d1 / (S * sigma * sqrt_T)

        # Theta (per day)
        term1 = -(S * pdf_d1 * sigma) / (2 * sqrt_T)
        if option_type == OptionType.CALL:
            theta = (term1 - r * K * exp_rT * _norm_cdf(d2)) / 365.0
        else:
            theta = (term1 + r * K * exp_rT * _norm_cdf(-d2)) / 365.0

        # Vega (per 1% vol move)
        vega = S * pdf_d1 * sqrt_T / 100.0

        # Rho (per 1% rate move)
        if option_type == OptionType.CALL:
            rho = K * T * exp_rT * _norm_cdf(d2) / 100.0
        else:
            rho = -K * T * exp_rT * _norm_cdf(-d2) / 100.0

        return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)

    @staticmethod
    def implied_volatility(
        market_price: float,
        S: float,
        K: float,
        T: float,
        r: float,
        option_type: OptionType = OptionType.CALL,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> float:
        """Calculate implied volatility via Newton-Raphson."""
        if T <= 0 or market_price <= 0:
            return 0.0

        sigma = 0.3  # initial guess

        for _ in range(max_iter):
            price = BlackScholes.price(S, K, T, r, sigma, option_type)
            vega_raw = BlackScholes._vega_raw(S, K, T, r, sigma)

            if vega_raw < 1e-10:
                break

            diff = price - market_price
            if abs(diff) < tol:
                return sigma

            sigma -= diff / vega_raw
            sigma = max(sigma, 0.001)
            sigma = min(sigma, 5.0)

        return sigma

    @staticmethod
    def full_pricing(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: OptionType = OptionType.CALL,
    ) -> OptionPricingResult:
        """Complete pricing: price + greeks + moneyness."""
        theo = BlackScholes.price(S, K, T, r, sigma, option_type)
        g = BlackScholes.greeks(S, K, T, r, sigma, option_type)

        if option_type == OptionType.CALL:
            intrinsic = max(S - K, 0)
        else:
            intrinsic = max(K - S, 0)

        ratio = S / K if K else 1.0
        if ratio > 1.02:
            moneyness = "ITM" if option_type == OptionType.CALL else "OTM"
        elif ratio < 0.98:
            moneyness = "OTM" if option_type == OptionType.CALL else "ITM"
        else:
            moneyness = "ATM"

        return OptionPricingResult(
            theoretical_price=theo,
            intrinsic_value=intrinsic,
            time_value=max(theo - intrinsic, 0),
            greeks=g,
            implied_vol=sigma,
            moneyness=moneyness,
        )

    # --- internals ---

    @staticmethod
    def _d1d2(
        S: float, K: float, T: float, r: float, sigma: float
    ) -> tuple[float, float]:
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        return d1, d2

    @staticmethod
    def _vega_raw(S: float, K: float, T: float, r: float, sigma: float) -> float:
        """Raw vega (not divided by 100) for Newton-Raphson."""
        if T <= 0 or sigma <= 0:
            return 0.0
        d1, _ = BlackScholes._d1d2(S, K, T, r, sigma)
        return S * _norm_pdf(d1) * math.sqrt(T)


# ---------------------------------------------------------------------------
# Synthetic option chain generator (for demo / testing)
# ---------------------------------------------------------------------------


def generate_option_chain(
    underlying_symbol: str,
    underlying_price: float,
    expiry: date,
    r: float = 0.03,
    base_vol: float = 0.25,
    num_strikes: int = 7,
    strike_step: Optional[float] = None,
) -> OptionChain:
    """Generate a synthetic option chain around the underlying price."""
    if strike_step is None:
        strike_step = round(underlying_price * 0.02, 2)
        strike_step = max(strike_step, 0.5)

    atm = round(underlying_price / strike_step) * strike_step
    half = num_strikes // 2
    strikes = [round(atm + (i - half) * strike_step, 2) for i in range(num_strikes)]

    T = max((expiry - date.today()).days, 1) / 365.0
    calls, puts = [], []

    for K in strikes:
        # Volatility smile: higher vol for OTM options
        moneyness_ratio = abs(math.log(underlying_price / K)) if K > 0 else 0
        vol = base_vol + moneyness_ratio * 0.3

        call_price = BlackScholes.price(underlying_price, K, T, r, vol, OptionType.CALL)
        put_price = BlackScholes.price(underlying_price, K, T, r, vol, OptionType.PUT)

        spread = max(call_price * 0.05, 0.01)

        calls.append(
            OptionContract(
                symbol=underlying_symbol,
                option_type=OptionType.CALL,
                strike=K,
                expiry=expiry,
                underlying_price=underlying_price,
                bid=round(max(call_price - spread, 0.01), 4),
                ask=round(call_price + spread, 4),
                last_price=round(call_price, 4),
                volume=int(1000 * (1 + moneyness_ratio * 2)),
                open_interest=int(5000 * (1 + moneyness_ratio)),
                implied_vol=round(vol, 4),
            )
        )

        puts.append(
            OptionContract(
                symbol=underlying_symbol,
                option_type=OptionType.PUT,
                strike=K,
                expiry=expiry,
                underlying_price=underlying_price,
                bid=round(max(put_price - spread, 0.01), 4),
                ask=round(put_price + spread, 4),
                last_price=round(put_price, 4),
                volume=int(800 * (1 + moneyness_ratio * 2)),
                open_interest=int(4000 * (1 + moneyness_ratio)),
                implied_vol=round(vol, 4),
            )
        )

    return OptionChain(
        underlying_symbol=underlying_symbol,
        underlying_price=underlying_price,
        expiry=expiry,
        calls=calls,
        puts=puts,
    )
