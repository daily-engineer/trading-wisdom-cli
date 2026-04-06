# CLI 框架设计

## 命令结构

```
trading-cli
├── data       📊 数据管理
├── analyze    🤖 AI分析
├── strategy   📈 策略管理
├── trade      💹 交易执行
├── monitor    👁️  实时监控
├── config     ⚙️  配置管理
├── workflow   🔄 工作流编排
├── report     📋 报告生成
└── debug      🐛 调试工具
```

## 主要命令群组

### data - 数据管理 ✅ 已实现 (Phase 1 Week 2)
```bash
trading-cli data fetch 000001.SZ                   # 获取股票数据
trading-cli data fetch 600519 --days 60            # 指定历史天数
trading-cli data sources                           # 查看数据源状态
trading-cli data validate 000001.SZ                # 验证股票代码
```

**支持市场：** A股 (Tushare)

### analyze - AI分析 ✅ 已实现 (Phase 1 Week 3)
```bash
trading-cli analyze indicators 000001.SZ          # 技术指标计算
trading-cli analyze indicators 600519 --days 120   # 指定历史天数
trading-cli analyze signal 000001.SZ               # 交易信号分析
trading-cli analyze summary 000001.SZ              # 快速技术摘要
```

**已支持指标：**
- 移动平均线 (SMA, EMA: 5/10/20/60)
- RSI (14)
- MACD (12, 26, 9)
- 布林带 (20, 2σ)
- ATR (14)
- 随机指标 (%K, %D)
- OBV
- CCI (20)

**信号分析：**
- 趋势判断 (EMA 金叉/死叉)
- RSI 超买超卖
- MACD 交叉信号
- 布林带位置
- 随机指标

### strategy - 策略管理 ✅ 已实现 (Phase 2 Week 4)
```bash
trading-cli strategy list                           # 列出所有策略
trading-cli strategy show ma_cross                   # 查看策略详情
trading-cli strategy create ma_cross                 # 注册内置策略
trading-cli strategy create my_strategy             # 创建自定义策略
trading-cli strategy delete my_strategy             # 删除自定义策略
```

**内置策略:**
- `ma_cross` - 移动平均线交叉策略
- `rsi` - RSI均值回归策略
- `macd` - MACD策略
- `bollinger` - 布林带策略

### backtest - 回测系统 ✅ 已实现 (Phase 2 Week 5)
```bash
trading-cli backtest run ma_cross 000001.SZ         # 运行回测
trading-cli backtest run rsi 600519 --capital 50000 # 指定资金
trading-cli backtest run bollinger 000001.SZ --params '{"period": 30}'
trading-cli backtest compare 000001.SZ              # 比较所有策略
trading-cli backtest history                         # 查看回测历史
```

**回测指标:**
- 总收益/收益率
- 交易次数/胜率
- 最大回撤
- 夏普比率

### trade - 交易执行
```bash
trading-cli trade order place buy --symbol 000001.SZ --quantity 100
trading-cli trade account balance
trading-cli trade position list
trading-cli trade risk check
```

### monitor - 实时监控
```bash
trading-cli monitor dashboard --refresh 5s
trading-cli monitor alert add --condition "drawdown > 15%"
trading-cli monitor options --watch delta,theta,vega
```

详细信息见完整设计文档。
