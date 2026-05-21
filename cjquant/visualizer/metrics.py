import pandas as pd
import numpy as np

class QualityMetrics:
    @staticmethod
    def calculate(daily_stats: pd.DataFrame, rf=0.02) -> dict:
        """
        输入 engine.export_results_csv 产生的 DataFrame
        """
        nav = daily_stats['total_assets']
        returns = daily_stats['daily_return']
        
        total_return = nav.iloc[-1] / nav.iloc[0] - 1
        annual_return = (1 + total_return) ** (252 / len(nav)) - 1
        annual_vol = returns.std() * np.sqrt(252)
        
        sharpe = (annual_return - rf) / annual_vol if annual_vol != 0 else 0
        
        downside_returns = returns[returns < 0]
        downside_vol = downside_returns.std() * np.sqrt(252)
        sortino = (annual_return - rf) / downside_vol if downside_vol != 0 else 0
        
        cum_max = nav.cummax()
        drawdown = (nav - cum_max) / cum_max
        max_drawdown = drawdown.min()
        
        calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        avg_cash_ratio = (daily_stats['available_cash'] + daily_stats['transit_cash']).mean() / daily_stats['total_assets'].mean()

        return {
            "累计收益": f"{total_return:.2%}",
            "年化收益": f"{annual_return:.2%}",
            "年化波动": f"{annual_vol:.2%}",
            "最大回撤": f"{max_drawdown:.2%}",
            "夏普比率": f"{sharpe:.2f}",
            "索提诺比率": f"{sortino:.2f}",
            "卡玛比率": f"{calmar:.2f}",
            "平均现金占比": f"{avg_cash_ratio:.2%}",
            "运行天数": len(nav)
        }