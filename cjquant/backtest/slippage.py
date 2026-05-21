from abc import ABC, abstractmethod
from typing import Callable

class BaseSlippage(ABC):
    @abstractmethod
    def get_impact_nav(self, current_nav: float, trade_value: float, direction: str) -> float:
        pass

class SquareRootSlippage(BaseSlippage):
    """
    针对 FOF 改进的平方根冲击模型。
    理论基础：大额申赎会迫使底层基金经理抛售股票，产生交易损耗，进而降低/抬高确认当天的净值。
    模型：Impact = lambda * NAV * sqrt(Trade_Value / Fund_AUM)
    """
    def __init__(self, impact_lambda: float = 0.1, fund_aum: float = 1e9):
        self.impact_lambda = impact_lambda
        self.fund_aum = fund_aum

    def get_impact_nav(self, current_nav: float, trade_value: float, direction: str) -> float:
        impact = self.impact_lambda * current_nav * ((trade_value / self.fund_aum) ** 0.5)
        # 买入时，基金净值被隐性抬高(更贵)；卖出时，基金净值被隐性砸低(更便宜)
        return current_nav + impact if direction == 'BUY' else current_nav - impact

class CustomLambdaSlippage(BaseSlippage):
    """支持研究员传入自定义 Lambda 表达式"""
    def __init__(self, func: Callable[[float, float, str], float]):
        self.func = func

    def get_impact_nav(self, current_nav: float, trade_value: float, direction: str) -> float:
        return self.func(current_nav, trade_value, direction)

class ZeroSlippage(BaseSlippage):
    def get_impact_nav(self, current_nav: float, trade_value: float, direction: str) -> float:
        return current_nav