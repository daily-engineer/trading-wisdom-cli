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

### data - 数据管理
```bash
trading-cli data fetch stock 000001.SZ
trading-cli data source add tushare --token xxx
trading-cli data stream subscribe --symbols AAPL,0700.HK
trading-cli data validate --symbol 000001.SZ
```

### analyze - AI分析
```bash
trading-cli analyze stock 000001.SZ
trading-cli analyze option SPY --expiry 2026-05-16
trading-cli analyze comprehensive AAPL --agents fundamental,technical,sentiment
```

### strategy - 策略管理
```bash
trading-cli strategy create my_strategy
trading-cli strategy backtest my_strategy --symbol 000001.SZ
trading-cli strategy optimize my_strategy --params "period=[20,50]"
trading-cli strategy deploy my_strategy --account live
```

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
