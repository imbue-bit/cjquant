from typing import List, Tuple

class OTCFeeModel:
    def __init__(self, buy_fee_rate: float = 0.0015):
        # 默认申购费 0.15% (通常平台打一折)
        self.buy_fee_rate = buy_fee_rate
        # 默认赎回费阶梯 (自然日天数, 费率)
        self.sell_fee_tiers: List[Tuple[int, float]] = [
            (7, 0.015),    # < 7天 收 1.5% 惩罚性费率
            (30, 0.0075),  # < 30天 收 0.75%
            (180, 0.005),  # < 180天 收 0.5%
            (float('inf'), 0.0) # >= 180天 免费
        ]

    def set_sell_tiers(self, tiers: List[Tuple[int, float]]):
        self.sell_fee_tiers = sorted(tiers, key=lambda x: x[0])

    def get_buy_fee(self, gross_amount: float) -> float:
        return gross_amount * self.buy_fee_rate

    def get_sell_fee_rate(self, holding_natural_days: int) -> float:
        """根据持有的自然日，匹配落入的费率阶梯"""
        for days_threshold, rate in self.sell_fee_tiers:
            if holding_natural_days < days_threshold:
                return rate
        return 0.0