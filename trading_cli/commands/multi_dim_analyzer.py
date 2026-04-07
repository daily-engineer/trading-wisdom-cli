"""Multi-dimensional analysis engine using BaoStock.

Provides 5-dimension diagnostic reports:
1. Valuation (PE/PB/PS/PCF vs historical percentile)
2. Fundamentals (ROE, growth, cash flow quality)
3. Technicals (MA trend, momentum)
4. Relative (industry peer comparison)
5. Sentiment (dividend yield, news)

Usage:
    trading-cli analyze multi 600519
    trading-cli analyze multi 000001 --peer 600036,601166,600919
    trading-cli analyze multi 000001 --scan industry=银行 --top 5
"""

from __future__ import annotations

import json
from typing import Optional

import click
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

console = Console()


# ──────────────────────────────────────────────
# BaoStock helpers
# ──────────────────────────────────────────────

def _bs_login():
    """Lazy import + login."""
    import baostock as bs
    bs.login()
    return bs


def _bs_logout(bs):
    try:
        bs.logout()
    except Exception:
        pass


def _bs_query(bs, func_name: str, **kwargs) -> Optional[pd.DataFrame]:
    """Generic BaoStock query → DataFrame."""
    fn = getattr(bs, func_name, None)
    if not fn:
        return None
    rs = fn(**kwargs)
    if rs.error_code != "0":
        return None
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    return pd.DataFrame(rows, columns=rs.fields)


def _cn2aotcn(cn_code: str) -> str:
    """Convert 000001.SZ → sz.000001 for BaoStock."""
    parts = cn_code.upper().replace("A", "").split(".")
    if len(parts) == 2:
        code, exchange = parts
        return f"{exchange.lower()}.{code}"
    # Fallback: assume SZ
    return f"sz.{cn_code.replace('.SZ', '').replace('.SH', '')}"


def _aotcn2code(a_code: str) -> str:
    """Convert sz.000001 → 000001.SZ for display."""
    if "." not in a_code:
        return a_code
    ex, code = a_code.split(".", 1)
    exchange = "SH" if ex.lower() == "sh" else "SZ"
    return f"{code}.{exchange}"


def _safe_float(val) -> Optional[float]:
    """Safe float conversion."""
    if val is None or val == "" or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ──────────────────────────────────────────────
# Dimension 1: Valuation
# ──────────────────────────────────────────────

def _analyze_valuation(bs, a_code: str, days: int = 180) -> dict:
    """PE/PB/PS/PCF + historical percentile."""
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    df = _bs_query(bs, "query_history_k_data_plus",
        code=a_code,
        fields="date,close,peTTM,pbMRQ,psTTM,pcfNcfTTM",
        start_date=start, end_date=end, frequency="d")

    if df is None or df.empty:
        return {"error": "No valuation data"}

    for c in ['close', 'peTTM', 'pbMRQ', 'psTTM', 'pcfNcfTTM']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    result = {}
    for metric in ['peTTM', 'pbMRQ', 'psTTM', 'pcfNcfTTM']:
        series = df[metric].dropna()
        if series.empty:
            result[metric] = None
        else:
            result[metric] = {
                "latest": round(series.iloc[-1], 3),
                "mean": round(series.mean(), 3),
                "p10": round(series.quantile(0.1), 3),
                "p90": round(series.quantile(0.9), 3),
                "percentile": round(df[metric].rank(pct=True).iloc[-1] * 100, 1),
            }

    result["close"] = round(df["close"].iloc[-1], 2)
    return result


# ──────────────────────────────────────────────
# Dimension 2: Fundamentals
# ──────────────────────────────────────────────

def _analyze_fundamentals(bs, a_code: str) -> dict:
    """ROE, growth, cash flow quality."""
    result = {}

    # Try latest available year/quarter
    for year in [2024, 2023, 2022]:
        for q in [4, 3, 2, 1]:
            # Profitability
            df = _bs_query(bs, "query_profit_data",
                code=a_code, year=year, quarter=q)
            if df is not None and not df.empty:
                r = df.iloc[0]
                result["profit"] = {
                    "year": year, "quarter": q,
                    "statDate": r.get("statDate", ""),
                    "roeAvg": _safe_float(r.get("roeAvg")),
                    "npMargin": _safe_float(r.get("npMargin")),
                    "epsTTM": _safe_float(r.get("epsTTM")),
                    "netProfit": _safe_float(r.get("netProfit")),
                }
                break
        if "profit" in result:
            break

    # Growth (same year)
    if "profit" in result:
        y, q = result["profit"]["year"], result["profit"]["quarter"]
        df = _bs_query(bs, "query_growth_data",
            code=a_code, year=y, quarter=q)
        if df is not None and not df.empty:
            r = df.iloc[0]
            result["growth"] = {
                "yoyEquity": _safe_float(r.get("YOYEquity")),
                "yoyAsset": _safe_float(r.get("YOYAsset")),
                "yoyNI": _safe_float(r.get("YOYNI")),
                "yoyEPS": _safe_float(r.get("YOYEPSBasic")),
            }

        # Balance / cash flow
        df = _bs_query(bs, "query_balance_data",
            code=a_code, year=y, quarter=q)
        if df is not None and not df.empty:
            r = df.iloc[0]
            result["balance"] = {
                "yoyLiability": _safe_float(r.get("YOYLiability")),
                "assetToEquity": _safe_float(r.get("assetToEquity")),
            }

        df = _bs_query(bs, "query_cash_flow_data",
            code=a_code, year=y, quarter=q)
        if df is not None and not df.empty:
            r = df.iloc[0]
            result["cashflow"] = {
                "cfoToNP": _safe_float(r.get("CFOToNP")),
                "cfoToOR": _safe_float(r.get("CFOToOR")),
            }

    return result if result else {"error": "No fundamental data"}


# ──────────────────────────────────────────────
# Dimension 3: Technicals
# ──────────────────────────────────────────────

def _analyze_technicals(bs, a_code: str, days: int = 60) -> dict:
    """MA trend + momentum."""
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

    df = _bs_query(bs, "query_history_k_data_plus",
        code=a_code,
        fields="date,open,high,low,close,volume,pctChg",
        start_date=start, end_date=end, frequency="d")

    if df is None or df.empty:
        return {"error": "No price data"}

    df["close"] = pd.to_numeric(df["close"], errors='coerce')
    df["volume"] = pd.to_numeric(df["volume"], errors='coerce').fillna(0)

    for period in [5, 10, 20, 60]:
        df[f"ma{period}"] = df["close"].rolling(period).mean()

    latest = df.iloc[-1]
    close = float(latest["close"])

    # Determine trend
    ma5 = float(latest.get("ma5", close))
    ma10 = float(latest.get("ma10", close))
    ma20 = float(latest.get("ma20", close))
    ma60 = float(latest.get("ma60", 0)) if pd.notna(latest.get("ma60")) else None

    above = {
        "ma5": close > ma5,
        "ma10": close > ma10,
        "ma20": close > ma20,
    }
    if ma60 is not None:
        above["ma60"] = close > ma60

    # Momentum
    change_5d = (close / float(df.iloc[-5]["close"]) - 1) * 100 if len(df) >= 5 else None
    change_20d = (close / float(df.iloc[-20]["close"]) - 1) * 100 if len(df) >= 20 else None

    # Volume trend
    vol_avg_5 = df["volume"].tail(5).mean()
    vol_avg_20 = df["volume"].tail(20).mean()
    vol_trend = "放量" if vol_avg_5 > vol_avg_20 * 1.2 else ("缩量" if vol_avg_5 < vol_avg_20 * 0.8 else "平量")

    return {
        "close": round(close, 2),
        "ma5": round(ma5, 2), "above_ma5": above["ma5"],
        "ma10": round(ma10, 2), "above_ma10": above["ma10"],
        "ma20": round(ma20, 2), "above_ma20": above["ma20"],
        "ma60": round(ma60, 2) if ma60 else None, "above_ma60": above.get("ma60"),
        "change_5d": round(change_5d, 2) if change_5d else None,
        "change_20d": round(change_20d, 2) if change_20d else None,
        "vol_trend": vol_trend,
    }


# ──────────────────────────────────────────────
# Dimension 4: Peer Comparison
# ──────────────────────────────────────────────

def _analyze_peer_comparison(bs, a_code: str, peer_codes: list = None) -> list:
    """Compare PE/PB/PS/PCF with peers."""
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    codes = peer_codes or ["sh.600036", "sh.601166", "sh.600919", "sh.601398", "sh.601288"]
    # Always include target
    if a_code not in codes:
        codes.insert(0, a_code)

    results = []
    for code in codes:
        df = _bs_query(bs, "query_history_k_data_plus",
            code=code,
            fields="date,close,peTTM,pbMRQ,psTTM,pcfNcfTTM",
            start_date=start, end_date=end, frequency="d")
        if df is None or df.empty:
            continue

        for c in ['close', 'peTTM', 'pbMRQ', 'psTTM', 'pcfNcfTTM']:
            df[c] = pd.to_numeric(df[c], errors='coerce')

        last = df.iloc[-1]
        results.append({
            "code": code,
            "display": _aotcn2code(code),
            "close": round(last["close"], 2) if pd.notna(last["close"]) else None,
            "pe": _safe_float(last.get("peTTM")),
            "pb": _safe_float(last.get("pbMRQ")),
            "ps": _safe_float(last.get("psTTM")),
            "pcf": _safe_float(last.get("pcfNcfTTM")),
        })

    return results


# ──────────────────────────────────────────────
# Scoring Engine
# ──────────────────────────────────────────────

def _compute_scores(valuation: dict, fundamentals: dict, technicals: dict) -> dict:
    """5-dimension scoring engine."""
    scores = {}

    # 1. Valuation score (based on PE percentile - lower is better)
    pe_info = valuation.get("peTTM")
    if pe_info:
        pct = pe_info["percentile"]
        if pct < 15: scores["估值"] = 5
        elif pct < 35: scores["估值"] = 4
        elif pct < 65: scores["估值"] = 3
        elif pct < 85: scores["估值"] = 2
        else: scores["估值"] = 1
    else:
        scores["估值"] = 0

    # 2. Profitability score (ROE based)
    roe = fundamentals.get("profit", {}).get("roeAvg")
    if roe is not None:
        if roe > 0.15: scores["盈利能力"] = 5
        elif roe > 0.10: scores["盈利能力"] = 4
        elif roe > 0.07: scores["盈利能力"] = 3
        elif roe > 0.04: scores["盈利能力"] = 2
        else: scores["盈利能力"] = 1
    else:
        scores["盈利能力"] = 0

    # 3. Growth score
    yoy_ni = fundamentals.get("growth", {}).get("yoyNI")
    if yoy_ni is not None:
        if yoy_ni > 0.30: scores["成长性"] = 5
        elif yoy_ni > 0.15: scores["成长性"] = 4
        elif yoy_ni > 0.05: scores["成长性"] = 3
        elif yoy_ni > 0: scores["成长性"] = 2
        else: scores["成长性"] = 1
    else:
        scores["成长性"] = 0

    # 4. Technical score
    above_ma_count = sum([
        technicals.get("above_ma5", False),
        technicals.get("above_ma10", False),
        technicals.get("above_ma20", False),
        technicals.get("above_ma60", False) or False,
    ])
    if above_ma_count >= 4: scores["技术面"] = 5
    elif above_ma_count >= 3: scores["技术面"] = 4
    elif above_ma_count >= 2: scores["技术面"] = 3
    elif above_ma_count >= 1: scores["技术面"] = 2
    else: scores["技术面"] = 1

    # 5. Cash flow quality
    cfo_np = fundamentals.get("cashflow", {}).get("cfoToNP")
    if cfo_np is not None:
        if cfo_np > 2.0: scores["现金质量"] = 5
        elif cfo_np > 1.0: scores["现金质量"] = 4
        elif cfo_np > 0.5: scores["现金质量"] = 3
        elif cfo_np > 0: scores["现金质量"] = 2
        else: scores["现金质量"] = 1
    else:
        scores["现金质量"] = 0

    return scores


# ──────────────────────────────────────────────
# Formatting Helpers
# ──────────────────────────────────────────────

def _stars(score: int, max_score: int = 5) -> str:
    return "⭐" * score + "☆" * (max_score - score)


def _score_color(score: int) -> str:
    if score >= 4: return "green"
    if score >= 3: return "yellow"
    if score >= 2: return "orange3"
    return "red"
