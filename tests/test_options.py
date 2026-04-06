"""Tests for the options pricing engine, Greeks, and strategies."""

import math
from datetime import date, timedelta

import pytest

from trading_cli.core.options import (
    BlackScholes, OptionType, OptionContract, OptionChain, generate_option_chain,
)
from trading_cli.strategy.options_strategies import (
    OptionLeg, _payoff_at_expiry, covered_call, protective_put,
    bull_call_spread, bear_put_spread, iron_condor, straddle,
    backtest_option_strategy,
)


# ---------------------------------------------------------------------------
# Black-Scholes pricing
# ---------------------------------------------------------------------------

class TestBlackScholes:
    """Tests for the BS pricing model."""

    def test_call_price_positive(self):
        p = BlackScholes.price(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert p > 0

    def test_put_price_positive(self):
        p = BlackScholes.price(100, 100, 0.25, 0.05, 0.20, OptionType.PUT)
        assert p > 0

    def test_put_call_parity(self):
        """C - P = S - K*e^(-rT)."""
        S, K, T, r, sigma = 100, 100, 0.5, 0.05, 0.25
        call = BlackScholes.price(S, K, T, r, sigma, OptionType.CALL)
        put = BlackScholes.price(S, K, T, r, sigma, OptionType.PUT)
        parity = S - K * math.exp(-r * T)
        assert call - put == pytest.approx(parity, abs=1e-6)

    def test_deep_itm_call_near_intrinsic(self):
        p = BlackScholes.price(150, 100, 0.01, 0.05, 0.20, OptionType.CALL)
        assert p == pytest.approx(50, abs=1.0)

    def test_deep_otm_call_near_zero(self):
        p = BlackScholes.price(50, 100, 0.01, 0.05, 0.20, OptionType.CALL)
        assert p < 0.1

    def test_expired_option(self):
        call = BlackScholes.price(110, 100, 0, 0.05, 0.20, OptionType.CALL)
        assert call == pytest.approx(10, abs=0.01)
        put = BlackScholes.price(90, 100, 0, 0.05, 0.20, OptionType.PUT)
        assert put == pytest.approx(10, abs=0.01)

    def test_higher_vol_higher_price(self):
        p1 = BlackScholes.price(100, 100, 0.25, 0.05, 0.15, OptionType.CALL)
        p2 = BlackScholes.price(100, 100, 0.25, 0.05, 0.35, OptionType.CALL)
        assert p2 > p1


class TestGreeks:
    def test_atm_call_delta_near_half(self):
        g = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert 0.45 < g.delta < 0.65

    def test_put_delta_negative(self):
        g = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.PUT)
        assert g.delta < 0

    def test_call_put_delta_relation(self):
        """Call delta - Put delta ≈ 1."""
        gc = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        gp = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.PUT)
        assert gc.delta - gp.delta == pytest.approx(1.0, abs=0.01)

    def test_gamma_positive(self):
        g = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert g.gamma > 0

    def test_gamma_same_for_call_put(self):
        gc = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        gp = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.PUT)
        assert gc.gamma == pytest.approx(gp.gamma, abs=1e-6)

    def test_theta_negative_for_long(self):
        g = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert g.theta < 0

    def test_vega_positive(self):
        g = BlackScholes.greeks(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert g.vega > 0


class TestImpliedVolatility:
    def test_round_trip(self):
        """Price → IV → re-price should match."""
        S, K, T, r, vol = 100, 100, 0.25, 0.05, 0.30
        price = BlackScholes.price(S, K, T, r, vol, OptionType.CALL)
        iv = BlackScholes.implied_volatility(price, S, K, T, r, OptionType.CALL)
        assert iv == pytest.approx(vol, abs=0.001)

    def test_put_iv(self):
        S, K, T, r, vol = 100, 105, 0.5, 0.03, 0.25
        price = BlackScholes.price(S, K, T, r, vol, OptionType.PUT)
        iv = BlackScholes.implied_volatility(price, S, K, T, r, OptionType.PUT)
        assert iv == pytest.approx(vol, abs=0.001)

    def test_zero_price_returns_zero(self):
        assert BlackScholes.implied_volatility(0, 100, 100, 0.25, 0.05) == 0.0


class TestFullPricing:
    def test_moneyness_itm(self):
        r = BlackScholes.full_pricing(110, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert r.moneyness == "ITM"

    def test_moneyness_otm(self):
        r = BlackScholes.full_pricing(90, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert r.moneyness == "OTM"

    def test_time_value_positive(self):
        r = BlackScholes.full_pricing(100, 100, 0.25, 0.05, 0.20, OptionType.CALL)
        assert r.time_value > 0


# ---------------------------------------------------------------------------
# Option chain
# ---------------------------------------------------------------------------

class TestOptionChain:
    def test_generate_chain(self):
        exp = date.today() + timedelta(days=30)
        chain = generate_option_chain("TEST", 100, exp, num_strikes=7)
        assert len(chain.calls) == 7
        assert len(chain.puts) == 7
        assert chain.underlying_price == 100

    def test_chain_strikes_sorted(self):
        exp = date.today() + timedelta(days=30)
        chain = generate_option_chain("TEST", 100, exp)
        assert chain.strikes == sorted(chain.strikes)

    def test_atm_strike(self):
        exp = date.today() + timedelta(days=30)
        chain = generate_option_chain("TEST", 100, exp)
        assert abs(chain.atm_strike() - 100) < 5

    def test_contract_days_to_expiry(self):
        exp = date.today() + timedelta(days=30)
        chain = generate_option_chain("TEST", 100, exp)
        assert chain.calls[0].days_to_expiry == 30

    def test_contract_mid_price(self):
        exp = date.today() + timedelta(days=30)
        chain = generate_option_chain("TEST", 100, exp)
        c = chain.calls[0]
        assert c.mid_price == pytest.approx((c.bid + c.ask) / 2)


# ---------------------------------------------------------------------------
# Options strategies
# ---------------------------------------------------------------------------

class TestOptionsStrategies:
    def test_covered_call(self):
        result = covered_call(100, 105, 2.5)
        assert result.name == "Covered Call"
        assert result.max_profit > 0
        assert len(result.break_evens) == 1
        assert result.break_evens[0] < 100

    def test_protective_put(self):
        result = protective_put(100, 95, 3.0)
        assert result.name == "Protective Put"
        assert result.max_loss < 0
        assert len(result.break_evens) == 1

    def test_bull_call_spread(self):
        result = bull_call_spread(100, 95, 7.0, 105, 2.0)
        assert result.name == "Bull Call Spread"
        assert result.max_profit > 0
        assert result.max_loss < 0

    def test_bear_put_spread(self):
        result = bear_put_spread(100, 105, 7.0, 95, 2.0)
        assert result.name == "Bear Put Spread"
        assert result.max_profit > 0

    def test_iron_condor(self):
        result = iron_condor(100, 85, 0.5, 90, 1.5, 110, 1.5, 115, 0.5)
        assert result.name == "Iron Condor"
        # Iron condor is net credit strategy
        assert result.max_profit > 0

    def test_long_straddle(self):
        result = straddle(100, 100, 3.0, 3.0, side=1)
        assert result.name == "Long Straddle"
        assert result.max_loss < 0
        assert len(result.break_evens) == 2  # two break-evens

    def test_short_straddle(self):
        result = straddle(100, 100, 3.0, 3.0, side=-1)
        assert result.name == "Short Straddle"
        assert result.max_profit > 0

    def test_payoff_at_expiry_call(self):
        legs = [OptionLeg(OptionType.CALL, strike=100, side=1, premium=5)]
        assert _payoff_at_expiry(legs, 110) == 5.0  # (110-100) - 5
        assert _payoff_at_expiry(legs, 100) == -5.0  # 0 - 5
        assert _payoff_at_expiry(legs, 90) == -5.0   # 0 - 5

    def test_risk_reward_ratio(self):
        result = bull_call_spread(100, 95, 7.0, 105, 2.0)
        assert result.risk_reward_ratio > 0


class TestOptionsBacktest:
    def test_basic_backtest(self):
        strat = bull_call_spread(100, 95, 7.0, 105, 2.0)
        price_path = [100 + i * 0.2 for i in range(20)]  # rising prices
        result = backtest_option_strategy(strat, price_path, total_days=30)
        assert result.days_held == 20
        assert result.entry_price == 100
        assert result.exit_price > 100

    def test_empty_path(self):
        strat = bull_call_spread(100, 95, 7.0, 105, 2.0)
        result = backtest_option_strategy(strat, [], total_days=30)
        assert result.pnl == 0

    def test_backtest_has_greeks(self):
        strat = straddle(100, 100, 3.0, 3.0)
        price_path = [100 + i * 0.1 for i in range(10)]
        result = backtest_option_strategy(strat, price_path)
        assert "delta" in result.greeks_at_entry
        assert "delta" in result.greeks_at_exit
