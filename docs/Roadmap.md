# 执行路线图

## 16周项目计划

### Phase 1: MVP框架搭建 (Week 1-3) ✅ 完成
**目标**: 完成基础框架和初始功能

- Week 1: 项目初始化、CLI框架、配置系统 ✅
- Week 2: 数据层（Tushare集成）✅
- Week 3: 分析层基础（技术分析）✅

**可交付物**: 基础CLI + 数据源 + 技术分析 ✅

### Phase 2: 核心功能 (Week 4-7) ✅ 完成
**目标**: 完整的 9 个命令群组 + 交易流程闭环

- Week 4: 策略框架 ✅
  - [x] 策略定义模型 + 注册表
  - [x] 4个内置策略 (MA Cross, RSI, MACD, Bollinger)
  - [x] strategy 命令组 (create/list/show/delete)

- Week 5: 回测引擎 ✅
  - [x] 回测框架 + 信号执行
  - [x] 性能计算 (P&L, Win Rate, Max Drawdown, Sharpe)
  - [x] backtest 命令组 (run/compare/history)

- Week 6: 监控、报告、策略优化 ✅
  - [x] monitor 命令组 (dashboard/watch/alert)
  - [x] report 命令组 (portfolio/performance/export)
  - [x] 策略优化器 (grid_search + genetic_optimize)
  - [x] 增强 backtest compare + optimize 命令

- Week 7: 交易执行、工作流、调试 ✅
  - [x] trade 命令组 (order buy/sell/cancel, position list/close, account, risk)
  - [x] 订单模型 (市价/限价/止损) + 风控引擎
  - [x] 模拟交易引擎 (Paper Trading)
  - [x] workflow 命令组 (YAML pipeline 编排)
  - [x] debug 命令组 (connectivity/info/data-check)

**可交付物**: 完整9命令组 + data→analyze→strategy→backtest→trade→monitor→report 全闭环 ✅

**统计**: 99 tests | 6000+ 行代码 | 10 命令组 | 30+ CLI 子命令

### Phase 3: 期权支持 (Week 8-10)
**目标**: 完整的期权交易支持

- Week 8: 期权数据和Greeks计算
- Week 9: 期权分析和策略
- Week 10: 期权风控和对冲

**可交付物**: 期权链分析、价差交易、Greeks监控

### Phase 4: 国际市场 (Week 11-12)
**目标**: 港股和美股支持

- Week 11: IB集成、港美股数据
- Week 12: 港美期权交易

**可交付物**: 三市场（A/HK/US）统一支持

### Phase 5: 实盘交易 (Week 13-14)
**目标**: 实盘交易就绪

- Week 13: 账户管理、实盘执行
- Week 14: 安全审计、紧急停损、完整测试

**可交付物**: 可进行实盘交易

### Phase 6: 优化发布 (Week 15-16)
**目标**: 代码质量和上线

- 性能优化
- 代码质量检查
- Docker部署
- v1.0正式发布

---

## 技术选型共识 (Issue #5)

- **回测引擎**: vectorbt 优先 + backtrader 备选，统一接口层
- **交易执行**: vnpy (veighna) — Phase 5
- **期权回测**: 独立设计，不绑定 Phase 2 引擎
- **工期**: Claude bot 驱动下 11-12 周可完成

详见 docs/Framework-Analysis.md
