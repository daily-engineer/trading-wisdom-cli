# 交易框架综合对比分析

## 概述

本文档对主流开源交易框架进行横向评测，为 Trading Wisdom CLI 的技术选型提供决策依据。

## 框架横向评测

| 框架 | Stars | 定位 | 优势 | 劣势 |
|------|-------|------|------|------|
| **vnpy (veighna)** | 38.9k⭐ | 全栈交易平台 | 执行层最强、A股深度支持、社区活跃、CTA/价差/期权策略完整 | 无LLM能力、学习曲线陡、架构偏重 |
| **TradingAgents** | 47.5k⭐ | LLM多代理分析 | 多Agent协作、情感/基本面/技术面分析、社区热度高 | 仅模拟交易、无实盘能力、无执行层 |
| **ValueCell** | 10.2k⭐ | 多Agent自动化 | 多Agent架构、自动化程度高 | 仅支持加密交易所、无传统市场支持 |
| **vectorbt** | 7k⭐ | 向量化回测分析 | 100-1000x快、参数优化强、Pandas原生、活跃维护 | 无期权支持、Commons Clause License、依赖重 |
| **backtrader** | 21k⭐ | 事件驱动回测 | 成熟稳定、文档全面、社区模板多 | 2021年停更、无活跃维护 |
| **rqalpha** | 6.3k⭐ | A股回测 | A股本地化好、RiceQuant维护 | 港美股支持弱、生态封闭 |
| **backtesting.py** | 5.5k⭐ | 轻量回测 | 极简API、上手快 | 功能基础、不适合复杂策略 |

## 多市场支持矩阵

| 框架 | A股 | 港股 | 美股 | 期权 | 加密货币 |
|------|-----|------|------|------|----------|
| vnpy (veighna) | ✅ 深度支持 | ✅ IB/富途 | ✅ IB | ✅ 完整 | ✅ |
| TradingAgents | ⚠️ 分析层 | ⚠️ 分析层 | ⚠️ 分析层 | ❌ | ❌ |
| ValueCell | ❌ | ❌ | ❌ | ❌ | ✅ |
| vectorbt | ⚠️ 需自接数据 | ⚠️ 需自接数据 | ✅ YFinance | ❌ | ✅ CCXT |
| backtrader | ⚠️ 需自接数据 | ⚠️ 需自接数据 | ✅ | ⚠️ 基础 | ❌ |
| rqalpha | ✅ 深度支持 | ❌ | ❌ | ❌ | ❌ |

## 执行层能力对比

| 能力 | vnpy | backtrader | vectorbt | rqalpha |
|------|------|------------|----------|---------|
| 实盘交易 | ✅ 多券商 | ❌ | ❌ (PRO版有) | ❌ |
| 回测引擎 | ✅ 内置 | ✅ 成熟 | ✅ 极快 | ✅ A股 |
| 参数优化 | ⚠️ 基础 | ⚠️ 手动 | ✅ 内置组合扫描 | ⚠️ 基础 |
| 风控系统 | ✅ 完整 | ⚠️ 需自建 | ❌ | ⚠️ 基础 |
| 订单管理 | ✅ 完整 | ✅ 模拟 | ❌ | ❌ |
| 多资产并行 | ✅ | ⚠️ 单资产为主 | ✅ MultiIndex | ❌ |

## 本项目技术选型决策

基于以上分析，Trading Wisdom CLI 采用**组合集成**策略：

### 分层选型

| 层次 | 选型 | 理由 |
|------|------|------|
| **AI分析层** | 自研 (参考 TradingAgents) | TradingAgents 无实盘能力，取其多Agent架构思路自建 |
| **回测引擎** | **vectorbt 优先** + backtrader 备选 | vectorbt 速度快、维护活跃；通过统一接口层保留切换灵活性 |
| **交易执行层** | vnpy (veighna) | 执行层最强、A股深度支持、多市场多券商 |
| **期权回测** | 独立设计 (Phase 3) | vectorbt 不支持期权，Phase 3 单独评估 QuantLib 等方案 |
| **数据层** | Tushare(A股) + AkShare(期权) + IB API(港美股) | 覆盖三市场数据需求 |

### 回测引擎统一接口

```
trading_cli/core/backtest/
├── engine.py              # BacktestEngine Protocol 抽象接口
├── vectorbt_engine.py     # Phase 2 默认：快速筛选 + 参数优化
└── backtrader_engine.py   # 备选：事件驱动精细回测（按需引入）
```

### 关键约束

1. **vectorbt License**: Apache 2.0 + Commons Clause，放入可选依赖组，商用前需评估
2. **统一接口优先**: Phase 2 Week 1 先定义 BacktestEngine Protocol，再接入具体引擎
3. **期权模块独立**: Phase 3 期权回测不依赖 Phase 2 引擎选型

## 参考链接

- [vnpy/vnpy](https://github.com/vnpy/vnpy) — veighna 量化交易平台
- [TradingAgents](https://github.com/TradingAgents-AI/TradingAgents) — LLM多代理交易系统
- [vectorbt](https://github.com/polakowo/vectorbt) — 向量化回测分析
- [backtrader](https://github.com/mementum/backtrader) — 事件驱动回测框架
- [rqalpha](https://github.com/ricequant/rqalpha) — A股回测框架

---

*最后更新：2026-04-06*
*决策来源：Issue #5 讨论共识*
