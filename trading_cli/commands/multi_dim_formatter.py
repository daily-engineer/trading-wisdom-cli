"""Report formatting + scan mode for multi-dimension analysis."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED

from trading_cli.commands.multi_dim_analyzer import (
    _bs_login, _bs_logout, _cn2aotcn, _aotcn2code, _safe_float,
    _analyze_valuation, _analyze_fundamentals, _analyze_technicals,
    _analyze_peer_comparison, _compute_scores, _stars, _score_color,
)

console = Console()


# ──────────────────────────────────────────────
# Industry stock list (for scan mode)
# ──────────────────────────────────────────────

# Manually curated list of bank stocks for BaoStock
BANK_STOCKS = [
    ("sz.000001", "平安银行"), ("sh.600000", "浦发银行"),
    ("sh.600015", "华夏银行"), ("sh.600016", "民生银行"),
    ("sh.600036", "招商银行"), ("sh.601009", "南京银行"),
    ("sh.601128", "常熟银行"), ("sh.601166", "兴业银行"),
    ("sh.601169", "北京银行"), ("sh.601187", "厦门银行"),
    ("sh.601229", "上海银行"), ("sh.601288", "农业银行"),
    ("sh.601328", "交通银行"), ("sh.601398", "工商银行"),
    ("sh.601577", "长沙银行"), ("sh.601818", "光大银行"),
    ("sh.601838", "成都银行"), ("sh.601939", "建设银行"),
    ("sh.601963", "重庆银行"), ("sh.601997", "贵阳银行"),
    ("sh.601998", "中信银行"), ("sh.603323", "苏农银行"),
    ("sz.000001", "平安银行"), ("sz.002142", "宁波银行"),
    ("sz.002766", "郑州银行"), ("sz.002797", "苏州银行"),
    ("sz.002807", "江阴银行"), ("sz.002839", "张家港行"),
    ("sz.002926", "华西证券"),
]

# Remove duplicates, keep code→name mapping
BANK_STOCKS_DICT = {}
for code, name in BANK_STOCKS:
    BANK_STOCKS_DICT[code] = name

INDUSTRY_MAPS = {
    "银行": BANK_STOCKS_DICT,
}


# ──────────────────────────────────────────────
# Format Report
# ──────────────────────────────────────────────

def _format_report(symbol: str, a_code: str,
                   val: dict, fund: dict, tech: dict,
                   comps: list, scores: dict):
    """Render the full 5-dimension diagnostic report."""
    
    header = Panel(
        f"[bold cyan]{symbol}[/bold cyan] ({a_code}) — 5 维诊断报告\n"
        f"数据源: [bold yellow]BaoStock[/bold yellow] (免费/稳定/无需积分)",
        border_style="cyan", box=ROUNDED
    )
    console.print(header)

    # 1. Valuation
    _render_valuation(val)
    
    # 2. Fundamentals
    _render_fundamentals(fund)
    
    # 3. Technicals
    _render_technicals(tech)
    
    # 4. Peer Comparison
    _render_peers(a_code, comps)
    
    # 5. Scores + Verdict
    _render_scores_and_verdict(val, fund, tech, scores)


def _render_valuation(val: dict):
    table = Table(title="📐 1. 估值诊断 (PE/PB/PS/PCF vs 历史分位)",
                  box=ROUNDED, border_style="cyan")
    table.add_column("指标", justify="left", style="bold")
    table.add_column("当前值", justify="right", style="white")
    table.add_column("近180日均值", justify="right", style="dim")
    table.add_column("分位", justify="right", style="cyan")
    table.add_column("状态", justify="center")

    metrics = {
        "PE-TTM": "peTTM", "PB-MRQ": "pbMRQ",
        "PS-TTM": "psTTM", "PCF-TTM": "pcfNcfTTM",
    }
    for label, key in metrics.items():
        info = val.get(key)
        if info is None:
            table.add_row(label, "N/A", "—", "—", "⚪")
            continue
        
        pct = info.get("percentile", 0)
        if pct < 25:
            status = "[green]低估[/green]"
        elif pct < 55:
            status = "[yellow]合理[/yellow]"
        elif pct < 80:
            status = "[orange3]偏高[/orange3]"
        else:
            status = "[red]高估[/red]"
        
        table.add_row(
            label,
            str(info.get("latest", "—")),
            str(info.get("mean", "—")),
            f"{pct:.0f}%",
            status,
        )

    if "close" in val:
        table.caption = f"收盘价: {val['close']}"
    console.print(table)


def _render_fundamentals(fund: dict):
    if "error" in fund:
        console.print(Panel(f"📋 2. 基本面: [red]{fund['error']}[/red]", border_style="red"))
        return

    table = Table(title="📋 2. 基本面：财务健康度", box=ROUNDED, border_style="green")
    table.add_column("维度", justify="left", style="bold")
    table.add_column("指标", justify="left")
    table.add_column("数值", justify="right", style="white")
    table.add_column("评价", justify="center")

    # Profitability
    prof = fund.get("profit", {})
    if prof:
        roe = prof.get("roeAvg")
        if roe:
            roe_pct = roe * 100
            if roe > 0.15: ev = "[green]优秀[/green]"
            elif roe > 0.08: ev = "[yellow]一般[/yellow]"
            else: ev = "[red]偏弱[/red]"
            table.add_row("盈利能力", "ROE", f"{roe_pct:.1f}%", ev)
        
        np_margin = prof.get("npMargin")
        if np_margin:
            table.add_row("盈利能力", "净利润率", f"{np_margin*100:.1f}%", "")
        
        eps = prof.get("epsTTM")
        if eps:
            table.add_row("盈利能力", "EPS-TTM", f"{eps:.2f}元", "")

    # Growth
    growth = fund.get("growth", {})
    if growth:
        yoy_ni = growth.get("yoyNI")
        if yoy_ni is not None:
            if yoy_ni > 0.10: ev = "[green]增长[/green]"
            elif yoy_ni > 0: ev = "[yellow]微增[/yellow]"
            else: ev = "[red]下滑[/red]"
            table.add_row("成长性", "净利润YoY", f"{yoy_ni*100:.1f}%", ev)

    # Cash Flow
    cf = fund.get("cashflow", {})
    if cf:
        cfo_np = cf.get("cfoToNP")
        if cfo_np is not None:
            if cfo_np > 1.0: ev = "[green]利润有现金支撑[/green]"
            elif cfo_np > 0: ev = "[yellow]利润部分变现[/yellow]"
            else: ev = "[red]利润纸上富贵[/red]"
            table.add_row("现金质量", "经营现金流/净利润", f"{cfo_np:.2f}x", ev)

    # Balance
    bal = fund.get("balance", {})
    if bal:
        atm = bal.get("assetToEquity")
        if atm:
            table.add_row("杠杆", "资产/权益倍数", f"{atm:.1f}x", "[dim]银行典型高杠杆[/dim]")

    # Report date
    if prof.get("year"):
        table.caption = f"报告期: {prof['year']}Q{prof.get('quarter', 4)}"
    console.print(table)


def _render_technicals(tech: dict):
    if "error" in tech:
        console.print(Panel(f"📈 3. 技术面: [red]{tech['error']}[/red]", border_style="red"))
        return

    table = Table(title="📈 3. 技术面：趋势 + 动量", box=ROUNDED, border_style="blue")
    table.add_column("指标", justify="left", style="bold")
    table.add_column("数值", justify="right", style="white")
    table.add_column("状态", justify="center")

    table.add_row("收盘价", f"{tech['close']:.2f}", "")
    
    for ma_name in ['ma5', 'ma10', 'ma20', 'ma60']:
        above_key = f"above_{ma_name}"
        val = tech.get(ma_name)
        if val is None:
            continue
        above = tech.get(above_key, False)
        status = "[green]站上 ▲[/green]" if above else "[red]跌破 ▼[/red]"
        table.add_row(ma_name.upper(), f"{val:.2f}", status)

    c5 = tech.get("change_5d")
    if c5 is not None:
        color = "green" if c5 > 0 else "red"
        table.add_row("近5日涨跌", f"[{color}]{c5:+.2f}%[/{color}]", "")
    
    c20 = tech.get("change_20d")
    if c20 is not None:
        color = "green" if c20 > 0 else "red"
        table.add_row("近20日涨跌", f"[{color}]{c20:+.2f}%[/{color}]", "")

    table.add_row("量能趋势", tech.get("vol_trend", "未知"), "")
    console.print(table)


def _render_peers(a_code: str, comps: list):
    if not comps:
        console.print("[dim]🏦 4. 同行业对比: 无数据[/dim]")
        return

    table = Table(title="🏦 4. 同行业估值对比", box=ROUNDED, border_style="magenta")
    table.add_column("股票", justify="left", style="bold")
    table.add_column("PE(TTM)", justify="right", style="cyan")
    table.add_column("PB", justify="right", style="cyan")
    table.add_column("PS", justify="right", style="dim")
    table.add_column("PCF", justify="right", style="dim")

    # Sort by PE for ranking
    valid = [c for c in comps if c.get("pe") is not None]
    valid.sort(key=lambda x: x["pe"] if x["pe"] else 999)

    for c in valid:
        is_target = c["code"] == a_code
        row_style = "bold yellow" if is_target else ""
        marker = " ←" if is_target else ""
        
        table.add_row(
            f"{c['display']}{marker}" if is_target else c["display"],
            str(c["pe"]) if c["pe"] else "N/A",
            str(c["pb"]) if c["pb"] else "N/A",
            str(c["ps"]) if c["ps"] else "N/A",
            str(c["pcf"]) if c["pcf"] else "N/A",
            style=row_style,
        )

    console.print(table)


def _render_scores_and_verdict(val: dict, fund: dict, tech: dict, scores: dict):
    # Calculate scores
    avg = sum(scores.values()) / len(scores) if scores else 0
    
    # Remove zero scores from avg for cleaner reporting
    nonzero = [v for v in scores.values() if v > 0]
    avg_clean = sum(nonzero) / len(nonzero) if nonzero else 0

    table = Table(title=f"🗡️ Sasa's CFO 综合评分: {avg_clean:.1f} / 5.0",
                  box=ROUNDED, border_style="yellow" if avg_clean >= 3 else "red")
    table.add_column("维度", justify="left", style="bold")
    table.add_column("评分", justify="center", style="cyan")
    table.add_column("星级", justify="left", style="white")
    table.add_column("细节", justify="left")

    dim_detail = {
        "估值": f"PE分位 {val.get('peTTM', {}).get('percentile', 0):.0f}%",
        "盈利能力": f"ROE {fund.get('profit', {}).get('roeAvg', 0)*100:.1f}%",
        "成长性": f"净利YoY {fund.get('growth', {}).get('yoyNI', 0)*100:.1f}%",
        "现金质量": f"CFO/NP {fund.get('cashflow', {}).get('cfoToNP', 0):.2f}x",
        "技术面": f"MA站上 {sum(1 for k,v in tech.items() if k.startswith('above_') and v)}/4",
    }

    for dim, score in scores.items():
        color = _score_color(score)
        table.add_row(
            dim,
            f"[bold {color}]{score}[/bold {color}]/5",
            _stars(score),
            dim_detail.get(dim, ""),
        )

    console.print(table)

    # Verdict
    if avg_clean >= 4.0:
        verdict = "[green]🟢 值得配置 — 基本面+估值+趋势共振[/green]"
    elif avg_clean >= 3.0:
        verdict = "[yellow]⚪ 可小仓位试探 — 有亮点但成长性一般[/yellow]"
    elif avg_clean >= 2.0:
        verdict = "[orange3]🟡 观望 — 不值得下重注[/orange3]"
    else:
        verdict = "[red]🔴 回避 — 资本应放在更有回报的地方[/red]"

    # Action plan
    action_lines = [f"[bold]🗡️ 终裁: {verdict}[/bold]\n"]
    
    ma20 = tech.get("ma20", 0)
    close = tech.get("close", 0)
    
    if avg_clean >= 3.0 and ma20 > 0:
        entry_low = round(ma20 * 0.98, 2)
        entry_high = round(ma20, 2)
        stop = round(ma20 * 0.94, 2)
        target = round(ma20 * 1.08, 2)
        risk_pct = round((entry_low - stop) / entry_low * 100, 1)
        reward_pct = round((target - entry_low) / entry_low * 100, 1)
        ratio = round(reward_pct / risk_pct, 1) if risk_pct > 0 else 0

        # Dividend yield estimate (rough)
        dividend_yield = "N/A"
        pe = val.get("peTTM", {}).get("latest")
        np_margin = fund.get("profit", {}).get("npMargin")
        if pe and pe > 0:
            # Rough estimate: assume dividend payout ratio ~30% for banks
            dividend_yield = f"{30/pe:.1f}%"

        action_lines.extend([
            f"🎯 操作计划:",
            f"  • 仓位: ≤ 5% 总资金",
            f"  • 入区间: [cyan]{entry_low} - {entry_high}[/cyan] (MA20附近)",
            f"  • 止损: [red]{stop}[/red] (-{risk_pct}%)",
            f"  • 目标: [green]{target}[/green] (+{reward_pct}%)",
            f"  • 风报比: [bold]1 : {ratio}[/bold]",
            f"  • 股息收益率(估算): {dividend_yield}",
        ])
    else:
        action_lines.append("建议观望，等待更好时机。")

    panel = Panel("\n".join(action_lines), title="🗡️ CFO 终裁", border_style="yellow", box=ROUNDED)
    console.print(panel)


# ──────────────────────────────────────────────
# Scan Mode
# ──────────────────────────────────────────────

def _scan_mode(filter_expr: str, top_n: int):
    """Scan industry stocks and rank by score."""
    # Parse filter
    industry_name = None
    if "=" in filter_expr:
        key, filter_val = filter_expr.split("=", 1)
        if key.strip().lower() == "industry":
            industry_name = filter_val.strip()
    
    stock_list = INDUSTRY_MAPS.get(industry_name) if industry_name else None
    if not stock_list:
        console.print(f"[red]❌ 未知行业: {filter_expr}[/red]")
        console.print(f"[dim]支持的行业: {', '.join(INDUSTRY_MAPS.keys())}[/dim]")
        return

    console.print(f"\n[cyan]🔍 扫描行业: {industry_name} ({len(stock_list)} 只)[/cyan]")
    
    bs = _bs_login()
    results = []
    
    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(SpinnerColumn(), TextColumn("[cyan]{task.description}[/cyan]"),
                  transient=True) as progress:
        task = progress.add_task(f"扫描 {industry_name}...", total=len(stock_list))
        
        for code, name in stock_list.items():
            # Skip invalid codes
            display_code = _aotcn2code(code)
            
            val = _analyze_valuation(bs, code, days=180)
            if "error" in val:
                progress.advance(task)
                continue
            
            fund = _analyze_fundamentals(bs, code)
            tech = _analyze_technicals(bs, code, days=60)
            
            if not {"peTTM", "pbMRQ"}.issubset(v for v in val.keys() if val[v] is not None):
                if val.get("peTTM") is None:
                    progress.advance(task)
                    continue
            
            scores = _compute_scores(val, fund, tech)
            avg = sum(v for v in scores.values() if v > 0) / max(1, sum(1 for v in scores.values() if v > 0))
            
            pe_info = val.get("peTTM")
            pe_val = pe_info.get("latest", "N/A") if pe_info else "N/A"
            pb_info = val.get("pbMRQ")
            pb_val = pb_info.get("latest", "N/A") if pb_info else "N/A"
            
            results.append({
                "code": display_code,
                "name": name,
                "pe": pe_val,
                "pb": pb_val,
                "score": round(avg, 2),
                "pe_pct": pe_info.get("percentile", 0) if pe_info else 0,
                "roe": fund.get("profit", {}).get("roeAvg", 0) or 0,
                "growth": fund.get("growth", {}).get("yoyNI", 0) or 0,
            })
            
            progress.advance(task)
    
    _bs_logout(bs)
    
    if not results:
        console.print("[yellow]⚠️ 无有效数据[/yellow]")
        return
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_n]
    
    table = Table(title=f"🏆 {industry_name} 行业评分排行 (Top {top_n})",
                  box=ROUNDED, border_style="green")
    table.add_column("排名", justify="center", style="bold")
    table.add_column("代码", justify="left")
    table.add_column("名称", justify="left", style="bold")
    table.add_column("评分", justify="center", style="cyan")
    table.add_column("PE", justify="right")
    table.add_column("PB", justify="right")
    table.add_column("ROE", justify="right")
    table.add_column("净利增速", justify="right")

    for i, r in enumerate(results, 1):
        medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f"{i}"))
        score_color = _score_color(int(r["score"]))
        
        table.add_row(
            medal,
            r["code"],
            r["name"],
            f"[bold {score_color}]{r['score']:.1f}[/bold {score_color}]/5",
            str(r["pe"]) if r["pe"] != "N/A" else "N/A",
            str(r["pb"]) if r["pb"] != "N/A" else "N/A",
            f"{r['roe']*100:.1f}%",
            f"{r['growth']*100:.1f}%",
        )

    console.print(table)
