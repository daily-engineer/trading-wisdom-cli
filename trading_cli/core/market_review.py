"""Market review data layer — A-share indices, sector boards, and breadth.

Provides:
    fetch_indices()         → list[dict]   (Sina hq.sinajs.cn)
    fetch_sector_board()    → list[dict]   (东财 push2)
    fetch_market_breadth()  → dict         (stub / future Tushare)
    parse_sina_response()   → list[dict]   (internal, exposed for testing)
    format_change()         → str          (飞书 color tags)
    render_markdown()       → str
    render_json()           → str
"""

from __future__ import annotations

import json
import logging
import warnings
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Index definitions
# ---------------------------------------------------------------------------

INDEX_CODES = [
    "sh000001",
    "sh000300",
    "sz399001",
    "sz399006",
    "sh000688",
    "sh000905",
    "sh000016",
]

INDEX_NAMES: dict[str, str] = {
    "sh000001": "上证指数",
    "sh000300": "沪深300",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000905": "中证500",
    "sh000016": "上证50",
}

SINA_URL = (
    "http://hq.sinajs.cn/list="
    "sh000001,sh000300,sz399001,sz399006,sh000688,sh000905,sh000016"
)

EASTMONEY_URL = (
    "http://push2.eastmoney.com/api/qt/clist/get"
    "?cb=&pn=1&pz=50&po=1&np=1"
    "&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f3"
    "&fs=m:90+t:{board_type_id}+f:!50"
    "&fields=f2,f3,f12,f14&_=1"
)

BOARD_TYPE_IDS = {"industry": 2, "concept": 3}


# ---------------------------------------------------------------------------
# Sina response parser
# ---------------------------------------------------------------------------


def parse_sina_response(text: str) -> list[dict[str, Any]]:
    """Parse Sina hq.sinajs.cn GB2312 response text.

    Returns a list of dicts with keys:
        code, name, current, prev_close, change, change_pct, amount_yi

    On any parse failure for a single line, returns a dict with ``error=True``.
    """
    results: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for line in lines:
        # Example: var hq_str_sh000001="fields...";
        if "hq_str_" not in line:
            continue
        try:
            code_part = line.split("hq_str_")[1].split("=")[0]
            # Extract the quoted value
            inner = line.split('"')[1]
            if not inner:
                results.append({"code": code_part, "error": True})
                continue
            fields = inner.split(",")
            if len(fields) < 10:
                results.append({"code": code_part, "error": True})
                continue

            name = fields[0] or INDEX_NAMES.get(code_part, code_part)
            open_price = float(fields[1]) if fields[1] else 0.0
            prev_close = float(fields[2]) if fields[2] else 0.0
            current = float(fields[3]) if fields[3] else 0.0
            # fields[8] = volume (shares), fields[9] = amount (yuan)
            amount_yuan = float(fields[9]) if len(fields) > 9 and fields[9] else 0.0

            change = current - prev_close
            change_pct = (change / prev_close * 100) if prev_close != 0 else 0.0
            amount_yi = amount_yuan / 1e8  # convert to 亿

            results.append(
                {
                    "code": code_part,
                    "name": name,
                    "current": current,
                    "prev_close": prev_close,
                    "open": open_price,
                    "change": change,
                    "change_pct": change_pct,
                    "amount_yi": amount_yi,
                    "error": False,
                }
            )
        except Exception as exc:
            code_part = "unknown"
            try:
                code_part = line.split("hq_str_")[1].split("=")[0]
            except Exception:
                pass
            logger.warning("Failed to parse Sina line for %s: %s", code_part, exc)
            results.append({"code": code_part, "error": True})

    return results


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


def fetch_indices() -> list[dict[str, Any]]:
    """Fetch 7 A-share indices from Sina hq.sinajs.cn.

    Returns list of dicts.  On network failure, returns list of error dicts.
    """
    try:
        resp = requests.get(
            SINA_URL,
            timeout=5,
            headers={"Referer": "http://finance.sina.com.cn"},
        )
        resp.raise_for_status()
        # Sina returns GB2312; requests may auto-detect or not
        try:
            text = resp.content.decode("gb2312")
        except (UnicodeDecodeError, LookupError):
            text = resp.content.decode("utf-8", errors="replace")

        parsed = parse_sina_response(text)
        if not parsed:
            # Return error dicts for all known codes
            return [{"code": c, "error": True} for c in INDEX_CODES]
        return parsed
    except Exception as exc:
        logger.warning("fetch_indices failed: %s", exc)
        return [{"code": c, "error": True} for c in INDEX_CODES]


def fetch_sector_board(
    board_type: str = "industry", top_n: int = 5
) -> list[dict[str, Any]]:
    """Fetch sector rankings from 东财 push2.

    board_type: "industry" (行业板块) or "concept" (概念板块)
    top_n: number of top/bottom sectors to return (unused for slicing here;
           callers should slice the returned list).

    Returns list of dicts with keys: code, name, latest, change_pct.
    Returns [] on timeout or non-200 (graceful degradation).
    """
    board_id = BOARD_TYPE_IDS.get(board_type, 2)
    url = EASTMONEY_URL.format(board_type_id=board_id)
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code != 200:
            logger.warning(
                "fetch_sector_board non-200: %s (board=%s)",
                resp.status_code,
                board_type,
            )
            return []
        data = resp.json()
        diff = data.get("data", {}).get("diff", [])
        if diff is None:
            return []
        result = []
        for item in diff:
            try:
                result.append(
                    {
                        "code": str(item.get("f12", "")),
                        "name": str(item.get("f14", "")),
                        "latest": float(item.get("f2", 0) or 0),
                        "change_pct": float(item.get("f3", 0) or 0),
                    }
                )
            except Exception:
                continue
        return result
    except Exception as exc:
        logger.warning("fetch_sector_board failed (board=%s): %s", board_type, exc)
        return []


def fetch_market_breadth() -> dict[str, Any]:
    """Return market breadth stub (real implementation needs Tushare Token)."""
    return {
        "advancing": 0,
        "declining": 0,
        "flat": 0,
        "limit_up": 0,
        "limit_down": 0,
        "northbound": 0.0,
        "note": "实时数据需要 Tushare Token",
    }


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_change(value: float) -> str:
    """Return 飞书-compatible colored change string.

    Positive → green, negative → red, zero → plain.
    """
    if value > 0:
        return f"<font color='green'>+{value:.2f}%</font>"
    elif value < 0:
        return f"<font color='red'>{value:.2f}%</font>"
    else:
        return f"{value:.2f}%"


def render_markdown(
    indices: list[dict[str, Any]],
    sectors_industry: list[dict[str, Any]],
    sectors_concept: list[dict[str, Any]],
    breadth: dict[str, Any],
    mode: str,
) -> str:
    """Render 飞书-compatible Markdown review string."""
    lines: list[str] = []

    mode_label = "盘中行情" if mode == "intraday" else "收盘复盘"
    lines.append(f"## 📊 A 股日报 — {mode_label}\n")

    # --- Indices ---
    lines.append("### 主要指数\n")
    lines.append("| 指数 | 最新 | 涨跌幅 | 成交额(亿) |")
    lines.append("|------|------|--------|-----------|")
    for idx in indices:
        if idx.get("error"):
            lines.append(f"| {idx.get('code', '?')} | - | - | - |")
        else:
            change_str = format_change(idx.get("change_pct", 0.0))
            lines.append(
                f"| {idx.get('name', idx.get('code', '?'))} "
                f"| {idx.get('current', 0.0):.2f} "
                f"| {change_str} "
                f"| {idx.get('amount_yi', 0.0):.1f} |"
            )

    lines.append("")

    # --- Industry sectors ---
    if sectors_industry:
        lines.append("### 行业板块 TOP5\n")
        lines.append("| 板块 | 涨跌幅 |")
        lines.append("|------|--------|")
        for s in sectors_industry[:5]:
            change_str = format_change(s.get("change_pct", 0.0))
            lines.append(f"| {s.get('name', '?')} | {change_str} |")
        lines.append("")
    else:
        lines.append("### 行业板块\n")
        lines.append("> 数据暂不可用（东财接口超时）\n")

    # --- Concept sectors ---
    if sectors_concept:
        lines.append("### 概念板块 TOP5\n")
        lines.append("| 板块 | 涨跌幅 |")
        lines.append("|------|--------|")
        for s in sectors_concept[:5]:
            change_str = format_change(s.get("change_pct", 0.0))
            lines.append(f"| {s.get('name', '?')} | {change_str} |")
        lines.append("")

    # --- Market breadth ---
    lines.append("### 市场宽度\n")
    if breadth.get("advancing", 0) or breadth.get("declining", 0):
        lines.append(
            f"- 上涨: {breadth['advancing']}  下跌: {breadth['declining']}  平: {breadth['flat']}"
        )
        lines.append(f"- 涨停: {breadth['limit_up']}  跌停: {breadth['limit_down']}")
        lines.append(f"- 北向资金: {breadth['northbound']:.1f} 亿")
    else:
        note = breadth.get("note", "")
        lines.append(f"> {note}")

    return "\n".join(lines)


def render_json(
    indices: list[dict[str, Any]],
    sectors_industry: list[dict[str, Any]],
    sectors_concept: list[dict[str, Any]],
    breadth: dict[str, Any],
    mode: str,
) -> str:
    """Render review data as JSON string."""
    payload = {
        "mode": mode,
        "indices": indices,
        "sectors_industry": sectors_industry,
        "sectors_concept": sectors_concept,
        "breadth": breadth,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
