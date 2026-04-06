# Trading Wisdom CLI

An AI-powered, command-line driven trading framework supporting A-shares, Hong Kong stocks, US stocks, and options.

## Features

- 📊 **Multi-Market Support**: A-shares, Hong Kong stocks, US stocks
- 🤖 **AI-Driven Analysis**: LLM-based multi-agent analysis system
- 💹 **Options Trading**: Full support for options analysis and trading
- 🔄 **Complete Workflow**: From data → analysis → strategy → execution → monitoring
- 🔧 **CLI-First Design**: Everything through command line, fully scriptable
- 📈 **Professional Tools**: Backtesting, paper trading, risk management, reporting

## Quick Start

```bash
# Install
poetry install

# Basic usage
trading-cli data fetch stock 000001.SZ
trading-cli analyze stock AAPL --market US
trading-cli strategy backtest my_strategy
```

## Project Status

🚀 **Under Active Development** - Following 16-week roadmap

- Phase 1 (Week 1-3): MVP Framework
- Phase 2 (Week 4-7): Core Features
- Phase 3 (Week 8-10): Options Support
- Phase 4 (Week 11-12): International Markets
- Phase 5 (Week 13-14): Live Trading Ready
- Phase 6 (Week 15-16): Optimization & Release

## Documentation

See `/docs` for detailed documentation and `/workflows` for example workflows.

## License

MIT

## 🤝 贡献和反馈

我们欢迎任何反馈和建议！

### 💬 如何提出反馈

**最佳方式**：在 [Issues](https://github.com/daily-engineer/trading-wisdom-cli/issues) 中提出反馈

- 📝 **文档改进**: 选择"文档反馈或建议"模板
- 🏗️ **架构建议**: 在相关 Issue 中讨论
- 🚀 **功能建议**: 创建新 Issue

详见 [贡献指南](CONTRIBUTING.md) 和 [反馈指南](docs/FEEDBACK.md)。

### 📋 反馈关键话题

我们现在特别需要反馈：
- ✅ 16周计划的合理性
- ✅ 架构设计的完整性
- ✅ CLI 命令的易用性
- ✅ 技术选择的最优性

### 👥 核心贡献者

- Daily Engineer - 项目主导
- sasa - 技术评审和建议

