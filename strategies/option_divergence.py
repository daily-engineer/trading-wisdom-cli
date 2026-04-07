#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sasa's Option Divergence Strategy (期权背离策略引擎)
------------------------------------------------
核心理念：期权 K 线蕴含正股上没有的"聪明钱"信息。
场景：
1. 标的涨 (Up)，期权跌 (Down) -> 诱多 (Short Signal / Cover Calls)
2. 标的跌 (Down)，期权涨 (Up)   -> 抄底/逼空前兆 (Long Signal)
3. 标的横盘，期权爆量         -> 异动 (Alert)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import akshare as ak
import json

class OptionDivergenceStrategy:
    """期权背离策略"""

    def __init__(self, etf_code="510300", option_code=None):
        """
        初始化
        :param etf_code: 标的 ETF 代码 (如 沪深 300ETF = 510300)
        :param option_code: 期权合约代码 (若为空则自动抓取主力合约)
        """
        self.etf_code = etf_code
        self.option_code = option_code
        self.df_etf = pd.DataFrame()
        self.df_option = pd.DataFrame()
        self.signal_log = []

    def fetch_data(self, lookback_days=60):
        """获取标的与期权数据"""
        print(f"\n📡 [Sasa] 正在获取 {self.etf_code} 及其期权数据 (过去{lookback_days}天)...")
        
        # 1. 获取 ETF 数据
        try:
            print(f"   📈 拉取 ETF 历史数据 ({self.etf_code})...")
            start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            
            df_etf = ak.fund_etf_hist_em(symbol=self.etf_code, period="daily", 
                                         start_date=start_date, end_date=end_date)
            
            df_etf.rename(columns={
                "日期": "Date",
                "收盘": "Price",
                "涨跌幅": "Change"
            }, inplace=True)
            
            df_etf['Price'] = pd.to_numeric(df_etf['Price'], errors='coerce')
            df_etf['Date'] = pd.to_datetime(df_etf['Date'])
            self.df_etf = df_etf[["Date", "Price"]].sort_values("Date")
            print(f"   ✅ 获取 ETF 数据成功：{len(self.df_etf)} 条")
            
        except Exception as e:
            print(f"   ⚠️ 网络请求异常，切换本地模拟数据模式：{e}")
            self._generate_mock_etf_data(lookback_days)
            self._generate_mock_option_data()
            return True

        # 2. 获取期权合约数据
        try:
            # 如果没有指定 specific option，尝试从期权板里找一个流动性好的认购期权
            # 这里为了原型运行顺畅，我们假设已经知道一个代码，或者遍历找到"购"
            # 实际生产中，这部分应该是复杂的"主力合约选择逻辑"
            
            # 尝试获取主力/当前期权列表
            print(f"   🤔 正在检索期权合约列表 (寻找高流动性合约)...")
            df_board = ak.option_finance_board()
            
            # 筛选近月、认购 (购)、平值附近的合约
            # 这是一个简化的筛选逻辑
            df_board = df_board[df_board['合约简称'].str.contains("购")] # 只看 Call
            
            if not df_board.empty:
                # 取第一个作为示例 (实际应取成交量最大的)
                target_row = df_board.iloc[0]
                actual_code = target_row['合约编码']
                opt_name = target_row['合约简称']
            else:
                print("   ⚠️ 未找到可用期权合约，使用模拟数据演示逻辑。")
                self._generate_mock_option_data()
                return True

            self.option_code = actual_code
            print(f"   📉 选定期权合约：{opt_name} (代码：{self.option_code})")

            # 注意：AkShare 的历史期权日线接口 (option_sse_daily_sina) 经常不稳定
            # 这里我们尝试用东方财富接口 (如果可用)
            # 如果接口再次失败，为了不阻断代码演示，我们生成模拟数据
            # 实际使用时，请确保 AkShare 能够调通 option_sse_daily_sina 或类似接口
            
            # 模拟数据用于演示算法本身 (因为 AkShare 接口经常变动导致脚本跑不通)
            print("   ⚠️ 注意：为保证演示算法逻辑，此处生成模拟期权走势数据。")
            print("   💡 Sasa 提示：在实盘环境中替换为真实接口数据。")
            self._generate_mock_option_data()
            
            # 注释掉的真实接口尝试代码：
            # df_opt = ak.option_sse_daily_sina(symbol=actual_code)
            # 处理 df_opt ...

            return True

        except Exception as e:
            print(f"   ❌ 期权数据获取异常，切换模拟模式：{e}")
            self._generate_mock_option_data()
            return True # 返回 True 表示继续运行 (使用模拟数据)

    def _generate_mock_etf_data(self, lookback_days=60):
        """生成模拟 ETF 数据 (当网络异常时)"""
        print("   🤖 [Sasa] 正在生成演示用的模拟 ETF 数据...")
        dates = pd.date_range(end=datetime.now(), periods=40, freq='B')  # ~40 trading days
        prices = np.cumsum(np.random.randn(40) * 0.02) + 3.8 + np.sin(np.linspace(0, 3.14, 40)) * 0.1
        self.df_etf = pd.DataFrame({"Date": dates, "Price": prices})
        print("   ✅ 模拟 ETF 数据已生成。")

    def _generate_mock_option_data(self):
        """生成模拟的期权数据用于算法测试"""
        print("   🤖 [Sasa] 正在生成演示用的模拟期权数据...")
        
        if self.df_etf.empty:
            print("   ❌ 无 ETF 数据，无法生成模拟期权。")
            return
        
        # 基于 ETF 数据生成，但人为加入"背离"
        df = self.df_etf.copy().reset_index(drop=True)
        n = len(df)
        
        # 逻辑：前 80% 天跟随 ETF，最后 20% 天人为制造背离
        split_idx = int(n * 0.8)
        
        # 正常跟随部分 (带杠杆): 前 split_idx+1 个点
        normal_len = split_idx + 1
        if normal_len > 0 and normal_len <= n:
            df.loc[:split_idx, 'Price'] = df['Price'][:normal_len].values * 2 + 10 + np.random.randn(normal_len) * 0.5
        
        # 制造"背离"场景 (ETF 涨，期权跌/横盘 -> 诱多信号)
        last_part_len = n - normal_len
        if last_part_len > 0:
            opt_tail = np.linspace(15, 10, last_part_len) + np.random.randn(last_part_len) * 0.5
            df.loc[normal_len:, 'Price'] = opt_tail
        
        self.df_option = df[["Date", "Price"]].rename(columns={"Price": "OptPrice"}).copy()
        print("   ✅ 模拟数据已生成。")

    def calculate_signals(self):
        """计算背离信号"""
        if self.df_etf.empty or self.df_option.empty:
            print("❌ 数据不足，无法计算。")
            return

        print("\n🧮 [Sasa] 正在计算背离信号...")

        # 1. 数据合并与对齐
        df = pd.merge(self.df_etf, self.df_option, on="Date", how="inner")
        
        # 2. 计算收益率
        df['ETF_Change'] = df['Price'].pct_change()
        df['Opt_Change'] = df['OptPrice'].pct_change()
        
        # 3. 滚动相关性 (Rolling Correlation) - 窗口 5 天
        # correlation < 0 代表背离 (价格变动方向相反)
        df['Rolling_Corr'] = df['ETF_Change'].rolling(window=5).corr(df['Opt_Change'])
        
        # 4. 信号判定逻辑
        signals = []
        for index, row in df.iterrows():
            sig = {"Date": str(row['Date']), "ETF": row['Price'], "Opt": row['OptPrice'], "Correlation": row['Rolling_Corr']}
            
            # 逻辑 A: 强背离 (ETF 涨，期权跌 -> 诱多)
            if row['ETF_Change'] > 0.005 and row['Opt_Change'] < -0.02:
                sig['Signal'] = "🔴 强背离 (诱多)"
                sig['Action'] = "卖出 Call / 做空"
            # 逻辑 B: 强背离 (ETF 跌，期权涨 -> 资金潜伏)
            elif row['ETF_Change'] < -0.005 and row['Opt_Change'] > 0.02:
                sig['Signal'] = "🟢 强背离 (抄底)"
                sig['Action'] = "买入 Call / 潜伏"
            # 逻辑 C: 相关性破位 (长期相关，突然不相关了)
            elif row['Rolling_Corr'] < 0.0:
                sig['Signal'] = "⚠️ 背离预警"
                sig['Action'] = "观察"
            else:
                sig['Signal'] = "—"
                sig['Action'] = "持有/观望"
            
            signals.append(sig)
        
        df_signals = pd.DataFrame(signals)
        
        # 打印最近的信号
        last_signals = df_signals[df_signals['Signal'] != "—"].tail(3)
        if not last_signals.empty:
            print("\n🚨 最近检测到的异常信号:")
            print(last_signals.to_string(index=False))
        else:
            print("\n✨ 暂无明显背离信号。")

        # 保存完整数据供后续 Pine Script 生成使用
        self.analysis_result = df_signals
        return df_signals

    def generate_pine_script(self, output_path=None):
        """生成 TradingView Pine Script 代码"""
        if not hasattr(self, 'analysis_result'):
            print("❌ 请先运行 calculate_signals")
            return

        print("\n📝 [Sasa] 正在生成 TradingView Pine Script 代码...")
        
        # 生成一个简单的展示背离指标的 Pine Script
        # 这里我们不画 K 线 (因为 K 线在图表上已经有了)，我们画一个"背离度 (Divergence)"指标
        
        pine_script = """
//@version=5
indicator("Sasa Option Divergence Indicator", overlay=false)

// 这里展示的是逻辑代码，实际运行时 TradingView 会自动计算
// 我们可以在 Pine Script 中计算 ETF 和 期权的相关性
// 注意：在 TV 中，你需要把期权数据作为第二个 Symbol 引入 (通过 request.security)

etf_price = close // 假设当前图表是 ETF
opt_symbol = input.symbol("OPTION_SYMBOL", "期权合约代码或相关 ETF")
opt_price = request.security(opt_symbol, timeframe.period, close)

// 计算变动率
etf_chg = ta.change(etf_price)
opt_chg = ta.change(opt_price)

// 滚动相关性 (5 周期)
corr_val = ta.correlation(etf_chg, opt_chg, 5)

// 画图
plot(corr_val, color=color.yellow, linewidth=2, title="ETF-Opt 5 日相关性")
hline(0, "背离基准线", color=color.red, linestyle=hline.style_dotted)
hline(0.8, "强相关区", color=color.green, linestyle=hline.style_dashed)
hline(-0.8, "弱相关区", color=color.green, linestyle=hline.style_dashed)

// 信号背景色
bgcolor(corr_val < 0 ? color.new(color.red, 90) : color.new(color.blue, 95))

// 提示标签
if corr_val < 0
    label.new(bar_index, corr_val, "背离!", style=label.style_label_up, color=color.new(color.red, 30), textcolor=color.white)
"""
        
        if output_path:
            with open(output_path, 'w') as f:
                f.write(pine_script)
            print(f"✅ Pine Script 已保存至：{output_path}")
        else:
            print("✅ Pine Script 逻辑如下 (可直接复制到 TradingView):")
            print("-" * 40)
            print(pine_script)
            print("-" * 40)


if __name__ == "__main__":
    print("🚀 Sasa Option Divergence Strategy V1.0")
    print("="*40)
    
    # 初始化策略 (以沪深 300ETF 为例)
    strategy = OptionDivergenceStrategy(etf_code="510300")
    
    # 1. 获取数据 (内部处理了 AkShare 接口，失败自动用模拟数据演示逻辑)
    has_data = strategy.fetch_data()
    
    if has_data:
        # 2. 计算
        strategy.calculate_signals()
        
        # 3. 生成 Pine Script
        strategy.generate_pine_script(output_path="option_divergence_indicator.pine")
    
    print("\n🏁 分析结束。")
