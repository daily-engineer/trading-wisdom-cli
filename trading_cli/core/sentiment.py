"""Market breadth & sentiment calculation engine.

Pure functions — no I/O, no side effects.

Composite sentiment score (0-100) uses six weighted sub-indicators:
    advance_decline : 0.20
    pct_above_ma20  : 0.20
    pct_above_ma60  : 0.15
    turnover_ratio  : 0.15
    limit_up_ratio  : 0.15
    northbound      : 0.15

Classification thresholds:
    ≥ 80 → 极度贪婪
    60-79 → 偏乐观
    40-59 → 中性
    20-39 → 偏悲观
    < 20  → 极度恐惧
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Composite weight map
# ---------------------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "advance_decline": 0.20,
    "pct_above_ma20": 0.20,
    "pct_above_ma60": 0.15,
    "turnover_ratio": 0.15,
    "limit_up_ratio": 0.15,
    "northbound": 0.15,
}

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def normalize_ad_ratio(advancing: int, declining: int) -> float:
    """Return 0-100 representing advance/decline balance.

    advancing / (advancing + declining) * 100.
    Returns 50.0 when both are zero.

    Parameters
    ----------
    advancing:
        Number of stocks that advanced (close > prev close).
    declining:
        Number of stocks that declined (close < prev close).
    """
    total = advancing + declining
    if total == 0:
        return 50.0
    return float(advancing) / float(total) * 100.0


def normalize_turnover(current: float, avg: float) -> float:
    """Return 0-100 from the turnover ratio (current / avg).

    Ratio is capped at 2.0 then scaled linearly to 0-100.
    Returns 0.0 when avg is zero or negative.

    Parameters
    ----------
    current:
        Today's turnover rate (absolute or relative — units must match avg).
    avg:
        Rolling average turnover (e.g. 20-day rolling mean).
    """
    if avg <= 0:
        return 0.0
    ratio = current / avg
    capped = min(ratio, 2.0)
    return capped / 2.0 * 100.0


def normalize_northbound(flow_yi: float) -> float:
    """Return 0-100 from northbound (沪深港通) net daily flow in 亿 RMB.

    -100亿 → 0, 0亿 → 50, +100亿 → 100.  Clamped outside [-100, +100].

    Parameters
    ----------
    flow_yi:
        Net daily flow in 亿 RMB.  Positive = net buy, negative = net sell.
    """
    clamped = max(-100.0, min(100.0, float(flow_yi)))
    return (clamped + 100.0) / 200.0 * 100.0


def normalize_limit_ratio(limit_up: int, limit_down: int) -> float:
    """Return 0-100 from the limit-up / (limit-up + limit-down) fraction.

    Returns 50.0 when both are zero.

    Parameters
    ----------
    limit_up:
        Number of stocks hitting the daily price limit up.
    limit_down:
        Number of stocks hitting the daily price limit down.
    """
    total = limit_up + limit_down
    if total == 0:
        return 50.0
    return float(limit_up) / float(total) * 100.0


# ---------------------------------------------------------------------------
# Breadth utilities (operate on DataFrames)
# ---------------------------------------------------------------------------


def advance_decline_ratio(prices_df: pd.DataFrame) -> tuple[int, int]:
    """Return (advancing, declining) counts from a price DataFrame.

    Parameters
    ----------
    prices_df:
        DataFrame where each column is a stock and rows are daily closes,
        ordered chronologically.  At least two rows are required.
    """
    if prices_df.shape[0] < 2:
        return (0, 0)
    prev = prices_df.iloc[-2]
    curr = prices_df.iloc[-1]
    diff = curr - prev
    advancing = int((diff > 0).sum())
    declining = int((diff < 0).sum())
    return (advancing, declining)


def limit_up_down_count(
    prices_df: pd.DataFrame, limit_pct: float = 0.10
) -> tuple[int, int]:
    """Return (limit_up_count, limit_down_count) from a price DataFrame.

    Parameters
    ----------
    prices_df:
        Daily close prices, columns = stocks, rows = dates (chronological).
    limit_pct:
        Daily limit percentage (default 10% for A-shares).
    """
    if prices_df.shape[0] < 2:
        return (0, 0)
    prev = prices_df.iloc[-2]
    curr = prices_df.iloc[-1]
    pct_change = (curr - prev) / prev.replace(0, float("nan"))
    up = int((pct_change >= limit_pct * 0.99).sum())  # small tolerance
    down = int((pct_change <= -limit_pct * 0.99).sum())
    return (up, down)


def pct_above_ma(prices_df: pd.DataFrame, window: int) -> float:
    """Return % of stocks whose latest close is above their {window}-day MA.

    Parameters
    ----------
    prices_df:
        Daily close prices, columns = stocks, rows = dates (chronological).
    window:
        Moving average window (e.g. 20, 60).
    """
    if prices_df.shape[0] < window:
        return 0.0
    ma = prices_df.rolling(window).mean().iloc[-1]
    latest = prices_df.iloc[-1]
    n_total = latest.notna().sum()
    if n_total == 0:
        return 0.0
    n_above = int((latest > ma).sum())
    return float(n_above) / float(n_total) * 100.0


def turnover_ratio(current_turnover: float, rolling_avg_turnover: float) -> float:
    """Return current / 20-day average turnover.

    Parameters
    ----------
    current_turnover:
        Today's aggregate market turnover.
    rolling_avg_turnover:
        20-day rolling average turnover.
    """
    if rolling_avg_turnover <= 0:
        return 0.0
    return current_turnover / rolling_avg_turnover


def gap_ratio(
    open_prices: pd.Series, prev_close_prices: pd.Series
) -> tuple[float, float]:
    """Return (pct_gap_up, pct_gap_down) for today's open vs yesterday's close.

    Parameters
    ----------
    open_prices:
        Today's open prices (index = stock code).
    prev_close_prices:
        Yesterday's close prices (index = stock code, same symbols).
    """
    aligned_open, aligned_prev = open_prices.align(prev_close_prices, join="inner")
    safe_prev = aligned_prev.replace(0, float("nan"))
    gap = (aligned_open - safe_prev) / safe_prev
    n = gap.notna().sum()
    if n == 0:
        return (0.0, 0.0)
    pct_up = float((gap > 0).sum()) / float(n) * 100.0
    pct_down = float((gap < 0).sum()) / float(n) * 100.0
    return (pct_up, pct_down)


def northbound_flow(flow_yi: Optional[float] = None) -> float:
    """Return net northbound flow in 亿 RMB.

    Returns 0.0 if unavailable (API not configured).

    Parameters
    ----------
    flow_yi:
        Pre-fetched flow value.  Pass None to signal "unavailable".
    """
    if flow_yi is None:
        return 0.0
    return float(flow_yi)


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------


def composite_sentiment_score(
    ad_ratio: float,
    pct_above_ma20: float,
    pct_above_ma60: float,
    turnover_current: float,
    turnover_avg: float,
    limit_up: int,
    limit_down: int,
    northbound_flow_val: float,
) -> float:
    """Return a composite market sentiment score in [0, 100].

    Parameters
    ----------
    ad_ratio:
        Raw advance/decline — not yet normalised (advancing / declining counts
        will be derived internally).  Pass the *advancing count* here; the
        function requires ``ad_ratio`` to already be expressed as the advancing
        fraction 0-100 OR as a raw count pair.

        For convenience this parameter is interpreted as an already-normalised
        0-100 value if it is in [0, 100], otherwise it is clamped.
    pct_above_ma20:
        % of stocks trading above their 20-day moving average (0-100).
    pct_above_ma60:
        % of stocks trading above their 60-day moving average (0-100).
    turnover_current:
        Today's aggregate turnover (same unit as ``turnover_avg``).
    turnover_avg:
        20-day rolling average turnover.
    limit_up:
        Number of stocks hitting the upper daily limit.
    limit_down:
        Number of stocks hitting the lower daily limit.
    northbound_flow_val:
        Net northbound flow in 亿 RMB.
    """

    # Validate / handle NaN inputs gracefully
    def _safe(v: float, fallback: float = 50.0) -> float:
        if math.isnan(v) or math.isinf(v):
            return fallback
        return float(v)

    n_ad = _safe(float(ad_ratio), 50.0)
    n_ma20 = _safe(float(pct_above_ma20), 50.0)
    n_ma60 = _safe(float(pct_above_ma60), 50.0)
    n_turn = normalize_turnover(
        _safe(float(turnover_current), 1.0),
        _safe(float(turnover_avg), 1.0),
    )
    n_limit = normalize_limit_ratio(max(0, int(limit_up)), max(0, int(limit_down)))
    n_north = normalize_northbound(_safe(float(northbound_flow_val), 0.0))

    score = (
        n_ad * WEIGHTS["advance_decline"]
        + n_ma20 * WEIGHTS["pct_above_ma20"]
        + n_ma60 * WEIGHTS["pct_above_ma60"]
        + n_turn * WEIGHTS["turnover_ratio"]
        + n_limit * WEIGHTS["limit_up_ratio"]
        + n_north * WEIGHTS["northbound"]
    )
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

_THRESHOLDS: list[tuple[float, str, str]] = [
    (80.0, "极度贪婪", "Market is euphoric. Consider trimming positions."),
    (60.0, "偏乐观", "Sentiment is positive. Maintain or add selectively."),
    (40.0, "中性", "Market is neutral. Hold current strategy."),
    (20.0, "偏悲观", "Sentiment is weak. Exercise caution, reduce risk."),
    (0.0, "极度恐惧", "Market is in fear. Watch for capitulation / contrarian entry."),
]


def classify_sentiment(score: float) -> tuple[str, str]:
    """Return (label, action_hint) for a composite sentiment score.

    Parameters
    ----------
    score:
        Composite sentiment score in [0, 100].
    """
    for threshold, label, action in _THRESHOLDS:
        if score >= threshold:
            return (label, action)
    # Should never reach here, but guard against edge cases
    return ("极度恐惧", _THRESHOLDS[-1][2])
