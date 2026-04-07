"""ETF RPS (Relative Price Strength) scoring engine.

Pure functions — no I/O, no side effects.  All calculations are vectorised
with pandas/numpy.

RPS definition used here:
  For each ETF, compute the percentile rank of its total return over the
  window against the universe of ETFs.  Smooth with a rolling moving average
  (default 5 days) to reduce noise, then take the latest value.

Composite score:
  rps_composite = 0.2*rps_20 + 0.3*rps_60 + 0.3*rps_120 + 0.2*rps_250

Grading:
  A: rps >= 90
  B: 70 <= rps < 90
  C: 50 <= rps < 70
  D: rps < 50
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Default ETF universe
# ---------------------------------------------------------------------------

DEFAULT_ETF_UNIVERSE = [
    "510300.SH",  # 沪深300
    "510500.SH",  # 中证500
    "159915.SZ",  # 创业板100
    "588000.SH",  # 科创50
    "510050.SH",  # 上证50
    "159901.SZ",  # 深证100
    "512010.SH",  # 医疗
    "512880.SH",  # 证券
    "515000.SH",  # 地产
    "512690.SH",  # 酒
    "516160.SH",  # 新能源
    "159949.SZ",  # 创业板50
]

SECTOR_MAP: dict[str, str] = {
    "510300.SH": "宽基",
    "510500.SH": "宽基",
    "588000.SH": "宽基",
    "510050.SH": "宽基",
    "159915.SZ": "宽基",
    "159901.SZ": "宽基",
    "512010.SH": "医疗",
    "512880.SH": "金融",
    "515000.SH": "地产",
    "512690.SH": "消费",
    "516160.SH": "新能源",
    "159949.SZ": "宽基",
}

# Composite weight configuration
_WINDOWS = [20, 60, 120, 250]
_WEIGHTS: dict[int, float] = {20: 0.2, 60: 0.3, 120: 0.3, 250: 0.2}

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def calculate_rps(
    prices: pd.DataFrame,
    window: int,
    smooth: int = 5,
) -> pd.Series:
    """Compute cross-sectional RPS scores for a single time window.

    Parameters
    ----------
    prices:
        DataFrame with ETF codes as columns, trading dates as index, and
        adjusted close prices as values.
    window:
        Lookback period in trading days for return calculation.
    smooth:
        Moving-average window applied to the daily percentile rank time
        series before taking the latest value.  Pass ``1`` to disable.

    Returns
    -------
    pd.Series
        Index = ETF code, values = RPS score in [0, 100].
        ETFs with insufficient history are returned as ``NaN``.
    """
    if prices.empty or len(prices) < 2:
        return pd.Series(dtype=float)

    # Clip to available history; if window > available rows, still compute
    # with what we have (returns NaN naturally for too-short series)
    lookback = min(window, len(prices) - 1)

    # Total return over the window: (price_t / price_{t-lookback}) - 1
    # Use the last `lookback` rows plus the row before them as the base.
    if len(prices) > lookback:
        base = prices.iloc[-(lookback + 1)]
        latest = prices.iloc[-1]
        returns = (latest / base) - 1.0
    else:
        returns = pd.Series(np.nan, index=prices.columns)

    # ------------------------------------------------------------------
    # Smoothing: compute rolling percentile rank on daily return series
    # then take the mean of the last `smooth` ranks.
    # ------------------------------------------------------------------
    if smooth > 1 and len(prices) >= smooth + 1:
        # daily returns for the whole history
        daily_ret = prices.pct_change().dropna(how="all")

        # For each day, rank each ETF cross-sectionally (pct=True → [0,1])
        daily_ranks = daily_ret.rank(axis=1, pct=True) * 100  # → [0, 100]

        # Rolling mean of the last `smooth` daily ranks
        rolling_mean = daily_ranks.rolling(window=smooth, min_periods=1).mean()
        smoothed = rolling_mean.iloc[-1]  # latest smoothed rank

        # Blend: 50% instant-return rank + 50% smoothed daily rank
        instant_rank = returns.rank(pct=True) * 100
        result = 0.5 * instant_rank + 0.5 * smoothed
    else:
        result = returns.rank(pct=True) * 100

    return result.rename("rps")


def composite_rps(
    prices: pd.DataFrame,
    smooth: int = 5,
) -> pd.DataFrame:
    """Compute composite RPS across all standard windows.

    Parameters
    ----------
    prices:
        DataFrame with ETF codes as columns, dates as index, close prices.
    smooth:
        Smoothing MA window passed down to :func:`calculate_rps`.

    Returns
    -------
    pd.DataFrame
        Columns: code, rps_20, rps_60, rps_120, rps_250, rps_composite, grade
    """
    records: list[dict] = []

    # Pre-compute per-window RPS
    window_scores: dict[int, pd.Series] = {}
    for w in _WINDOWS:
        window_scores[w] = calculate_rps(prices, w, smooth=smooth)

    # Build per-ETF rows
    codes = list(prices.columns)
    for code in codes:
        row: dict = {"code": code}
        weighted_sum = 0.0
        total_weight = 0.0
        for w in _WINDOWS:
            col = f"rps_{w}"
            val = window_scores[w].get(code, np.nan)
            row[col] = val
            if not np.isnan(val):
                weighted_sum += _WEIGHTS[w] * val
                total_weight += _WEIGHTS[w]

        if total_weight > 0:
            composite = weighted_sum / total_weight
        else:
            composite = np.nan

        row["rps_composite"] = composite
        row["grade"] = classify_grade(composite) if not np.isnan(composite) else "N/A"
        records.append(row)

    df = pd.DataFrame(
        records,
        columns=[
            "code",
            "rps_20",
            "rps_60",
            "rps_120",
            "rps_250",
            "rps_composite",
            "grade",
        ],
    )
    return df.sort_values(
        "rps_composite", ascending=False, na_position="last"
    ).reset_index(drop=True)


def classify_grade(rps_score: float) -> str:
    """Map a composite RPS score to a letter grade.

    Parameters
    ----------
    rps_score:
        Numeric RPS value in [0, 100].

    Returns
    -------
    str
        'A', 'B', 'C', or 'D'.
    """
    if rps_score >= 90:
        return "A"
    if rps_score >= 70:
        return "B"
    if rps_score >= 50:
        return "C"
    return "D"
