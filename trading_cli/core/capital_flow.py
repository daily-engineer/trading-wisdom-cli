"""Capital flow calculation engine — pure functions for 大单/主力 flow analysis."""

from __future__ import annotations

import pandas as pd


def calculate_net_inflow(df: pd.DataFrame) -> pd.Series:
    """Calculate net inflow from large and extra-large orders.

    df must have columns:
        buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol, close

    Returns a Series with net_inflow (in CNY, using close price as proxy).
    Formula: (buy_lg_vol + buy_elg_vol - sell_lg_vol - sell_elg_vol) × close
    """
    net_vol = (
        df["buy_lg_vol"] + df["buy_elg_vol"] - df["sell_lg_vol"] - df["sell_elg_vol"]
    )
    return net_vol * df["close"]


def calculate_flow_intensity(net_inflow: pd.Series, total_vol: pd.Series) -> pd.Series:
    """Calculate flow intensity as a 0-100 scale.

    intensity = abs(net_inflow) / (total_vol × price) × 100

    When total_vol is zero the intensity is 0.
    net_inflow is already in CNY units; total_vol is in shares so we need to
    treat them consistently.  Since net_inflow = net_vol × close, the natural
    denominator is total_vol × close.  However the caller may pass total_vol
    already in value units (amount).  We accept both by normalising:
      - if net_inflow and total_vol have compatible units we compute ratio directly.

    For simplicity the implementation divides abs(net_inflow) by total_vol and
    clips to [0, 100].  When total_vol == 0 the result is 0.
    """
    with_zero = total_vol.replace(0, float("nan"))
    intensity = (net_inflow.abs() / with_zero * 100).fillna(0.0)
    return intensity.clip(0, 100)


def detect_signal(price_changes: pd.Series, net_inflows: pd.Series) -> pd.Series:
    """Classify each day as 吸筹 / 派发 / 中性.

    Rules:
        price_change < 0  AND net_inflow > 0  → 吸筹  (accumulation: smart money buying on weakness)
        price_change > 0  AND net_inflow < 0  → 派发  (distribution: smart money selling on strength)
        otherwise                              → 中性
    """

    def _classify(row: tuple[float, float]) -> str:
        pch, nif = row
        if pch < 0 and nif > 0:
            return "吸筹"
        if pch > 0 and nif < 0:
            return "派发"
        return "中性"

    pairs = list(zip(price_changes.tolist(), net_inflows.tolist()))
    result = [_classify(p) for p in pairs]
    return pd.Series(result, index=price_changes.index, name="signal")


def calculate_streak(net_inflows: pd.Series) -> int:
    """Return the current consecutive streak from the end of the series.

    Positive value → N consecutive days of net inflow (last N rows > 0).
    Negative value → N consecutive days of net outflow (last N rows < 0).
    Zero → the last day has zero net inflow, or the series is empty.
    """
    if len(net_inflows) == 0:
        return 0

    values = net_inflows.tolist()
    last = values[-1]

    if last == 0:
        return 0

    direction = 1 if last > 0 else -1
    streak = 0
    for v in reversed(values):
        if (direction == 1 and v > 0) or (direction == -1 and v < 0):
            streak += 1
        else:
            break

    return streak * direction
