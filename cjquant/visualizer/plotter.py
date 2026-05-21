import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
import seaborn as sns

class ReportPlotter:
    def __init__(self, daily_stats: pd.DataFrame, trade_history: pd.DataFrame = None):
        self.df = daily_stats
        self.trades = trade_history
        sns.set_theme(style="whitegrid")
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False

    def create_interactive_figure(self):
        fig = make_subplots(
            rows=4, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.05,
            row_heights=[0.4, 0.2, 0.2, 0.2],
            subplot_titles=("净值曲线", "每日回撤", "现金与头寸分布", "每日收益率")
        )

        # 1. 净值曲线
        fig.add_trace(go.Scatter(x=self.df.index, y=self.df['total_assets'], name="总资产", line=dict(color='royalblue', width=2)), row=1, col=1)
        
        # 2. 回撤曲线
        cum_max = self.df['total_assets'].cummax()
        drawdown = (self.df['total_assets'] - cum_max) / cum_max
        fig.add_trace(go.Scatter(x=self.df.index, y=drawdown, name="回撤", fill='tozeroy', line=dict(color='crimson')), row=2, col=1)

        # 3. 资产构成 (堆叠面积图)
        fig.add_trace(go.Scatter(x=self.df.index, y=self.df['market_value'], name="基金持仓", stackgroup='one', line=dict(width=0)), row=3, col=1)
        fig.add_trace(go.Scatter(x=self.df.index, y=self.df['transit_cash'], name="在途资金(Transit)", stackgroup='one', line=dict(width=0)), row=3, col=1)
        fig.add_trace(go.Scatter(x=self.df.index, y=self.df['available_cash'], name="可用现金", stackgroup='one', line=dict(width=0)), row=3, col=1)

        fig.add_trace(go.Bar(x=self.df.index, y=self.df['daily_return'], name="日收益率"), row=4, col=1)

        fig.update_layout(height=1000, title_text="CJQuant 策略回测分析报告", showlegend=True)
        return fig

    def create_static_summary(self, save_path=None):
        """生成 Matplotlib 静态汇总图"""
        fig, axes = plt.subplots(3, 1, figsize=(12, 15))
        
        self._plot_monthly_heatmap(axes[0])
        
        self.df['total_assets'].plot(ax=axes[1], color='blue', label='NAV')
        ax2 = axes[1].twinx()
        cum_max = self.df['total_assets'].cummax()
        dd = (self.df['total_assets'] - cum_max) / cum_max
        ax2.fill_between(dd.index, dd, 0, color='red', alpha=0.3, label='Drawdown')
        axes[1].set_title("净值走势与回撤区")
        
        if self.trades is not None and not self.trades.empty:
            self.trades['submit_date'] = pd.to_datetime(self.trades['submit_date'])
            self.trades.set_index('submit_date').resample('M').size().plot(kind='bar', ax=axes[2], color='gray')
            axes[2].set_title("月度交易笔数 (Turnover Analysis)")
        
        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        return fig

    def _plot_monthly_heatmap(self, ax):
        """生成经典的收益率热力图"""
        returns = self.df['daily_return']
        monthly_ret = returns.groupby([returns.index.year, returns.index.month]).apply(lambda x: (1+x).prod()-1).unstack()
        monthly_ret.columns = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        sns.heatmap(monthly_ret, annot=True, fmt=".2%", cmap="RdYlGn", center=0, ax=ax, cbar=False)
        ax.set_title("月度收益分布热力图")