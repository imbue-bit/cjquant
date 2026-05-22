from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple
from .model import PositionLot
from .fee import OTCFeeModel

class TransitCashAccount:
    def __init__(self, initial_cash: float):
        self.available_cash = initial_cash
        self.frozen_cash = 0.0 # 因提交BUY指令但未确认而冻结的资金
        self.transit_queue: Dict[datetime, float] = defaultdict(float) # {资金预计到达日: 金额}

    def process_daily_arrival(self, current_date: datetime):
        """每日引擎驱动将到期的 transit 资金解冻到可用资金池"""
        if current_date in self.transit_queue:
            arrived_cash = self.transit_queue.pop(current_date)
            self.available_cash += arrived_cash

    def lock_cash(self, amount: float):
        if self.available_cash < amount:
            raise ValueError(f"可用资金不足. 可用:{self.available_cash}, 需求:{amount}")
        self.available_cash -= amount
        self.frozen_cash += amount

    def add_to_transit(self, amount: float, settle_date: datetime):
        """赎回后，资金进入 T+n 队列"""
        self.transit_queue[settle_date] += amount

class FundPosition:
    """基于批次(Lot)的单只基金持仓管理 (遵循中登 FIFO 规则)"""
    def __init__(self, fund_code: str, fee_model: OTCFeeModel):
        self.fund_code = fund_code
        self.fee_model = fee_model
        self.lots: List[PositionLot] = [] # 按 confirm_date 升序排列
        self.frozen_shares = 0.0 # 提交了SELL指令但尚未确认的份额

    @property
    def total_shares(self) -> float:
        return sum(lot.shares for lot in self.lots)

    @property
    def total_available_shares(self) -> float:
        return self.total_shares - self.frozen_shares

    def add_lot(self, confirm_date: datetime, shares: float, unit_cost: float):
        self.lots.append(PositionLot(self.fund_code, confirm_date, shares, unit_cost))
        # 维持 FIFO 顺序
        self.lots.sort(key=lambda x: x.confirm_date)

    def process_sell(self, confirm_date: datetime, shares_to_sell: float, confirm_nav: float) -> Tuple[float, float, float]:
        """
        按照 FIFO 逐笔卖出，计算惩罚费率。
        返回: (总成交金额_gross, 扣除的总手续费, 净到账金额)
        """
        remaining_to_sell = shares_to_sell
        total_gross = 0.0
        total_fee = 0.0

        lots_to_remove = []

        for lot in self.lots:
            if remaining_to_sell <= 0:
                break
            
            # 计算这一批次的持有自然日 (这是公募基金强制要求的规则)
            holding_days = (confirm_date - lot.confirm_date).days
            fee_rate = self.fee_model.get_sell_fee_rate(holding_days)

            if lot.shares <= remaining_to_sell:
                # 这一批次被全部卖光
                sell_shares = lot.shares
                lots_to_remove.append(lot)
            else:
                # 这一批次只卖了一部分
                sell_shares = remaining_to_sell
                lot.shares -= sell_shares
            
            gross_val = sell_shares * confirm_nav
            fee_val = gross_val * fee_rate
            
            total_gross += gross_val
            total_fee += fee_val
            remaining_to_sell -= sell_shares

        for lot in lots_to_remove:
            self.lots.remove(lot)

        self.frozen_shares -= shares_to_sell
        return total_gross, total_fee, total_gross - total_fee